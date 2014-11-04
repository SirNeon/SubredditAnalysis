from collections import Counter
from datetime import datetime
import logging
from math import sqrt
import operator
import os
import sqlite3 as db
from sqlite3 import OperationalError
from socket import timeout
import praw
from praw.errors import *
from requests.exceptions import HTTPError
from simpleconfigparser import simpleconfigparser
from exceptions import *


class SubredditAnalysis(object):


    def __init__(self):
        """
        Initialize the class with some basic attributes.
        """

        # check for a banlist.txt file
        if(os.path.isfile("banlist.txt") == False):
            print("Could not find banlist.txt.")

        # check for settings.cfg file
        if(os.path.isfile("settings.cfg") == False):
            raise SettingsError("Could not find settings.cfg.")

        # needed to read the settings.cfg file
        self.config = simpleconfigparser()

        self.config.read("settings.cfg")

        # add terminal output
        self.verbose = self.config.main.getboolean("verbose")

        # maximum threads to crawl. Reddit doesn't
        # like it when you go over 1000
        self.scrapeLimit = int(self.config.main.scrapeLimit)

        # maximum amount of comments/submissions to crawl through in
        # a user's overview
        self.overviewLimit = int(self.config.main.overviewLimit)

        # don't include comments/submissions beneath this score
        self.minScore = int(self.config.main.minScore)

        # give drilldowns flair or not
        self.setflair = self.config.main.getboolean("setflair")

        # calculate similarity or not
        self.similarity = self.config.main.getboolean("similarity")

        # determines how many subreddits the bot calculates similarity for
        self.similarityLimit = int(self.config.main.similarityLimit)

        # sets the cap for sample size
        self.userLimit = int(self.config.main.userLimit)

        # post drilldown to this subreddit
        self.post_to = self.config.main.post_to

        self.useragent = "Reddit Analysis Bot by /u/SirNeon"

        # optional logging
        self.infoLogging = self.config.logging.getboolean("infoLogging")
        self.postLogging = self.config.logging.getboolean("postLogging")
        self.errorLogging = self.config.logging.getboolean("errorLogging")

        # banned defaults and former defaults since
        # reddit autosubscribes users to them
        self.banList = []

        # list of users found in the target subreddit
        self.userList = []

        # list of overlapping subreddits
        self.subredditList = []

        if(self.config.main.getboolean("banList")):
            with open("banlist.txt", 'r') as f:
                for subreddit in f.readlines():
                    subreddit = subreddit.strip('\n')
                    self.banList.append(subreddit)

    
    def add_msg(self, msg=None, newline=False):
        """
        Simple function to make terminal output optional. Feed
        it the message to print out. Can also tell it to print a 
        newline if you want to.
        """

        if(self.verbose):
            if msg is not None:
                print(msg)

            if(newline):
                print('\n')


    def login(self, username, password):
        """
        This function logs the bot into its Reddit account.
        It takes 2 arguments: the username and the password.
        """

        self.client = praw.Reddit(user_agent=self.useragent)
        print("Logging in as {0}...".format(username))
        

        self.client.login(username, password)
        print("Login successful.")


    def get_users(self, subreddit):
        """
        This function creates a list of users that posted in
        the subreddit which is being scanned. The data from these
        users is then collected to determine where else they post.
        It takes 1 argument, which is the subreddit to be scanned.
        It returns a list of users.
        """

        print("Getting users for /r/{0}...".format(subreddit))

        while True:
            try:
                # get threads from the hot list
                submissions = self.client.get_subreddit(subreddit).get_hot(limit=self.scrapeLimit)
                break

            except (ConnectionResetError, HTTPError, timeout) as e:
                self.add_msg(e)
                continue
        
        # get the thread creator and if he's not
        # in the userList then add him there
        for i, submission in enumerate(submissions):
            if len(self.userList) > self.userLimit:
                return self.userList

            try:
                submitter = str(submission.author)
                subScore = int(submission.score)

            except AttributeError:
                continue

            # exclude submitters of posts beneath this threshold
            if subScore > self.minScore:
                # make sure that users don't get added multiple times
                if submitter not in self.userList:
                    self.userList.append(submitter)
                    print("\r{0} users found up to thread ({1} / {2}).".format(len(self.userList), i + 1, self.scrapeLimit), end='')


            while True:
                try:
                    # load more comments
                    submission.replace_more_comments(limit=None, threshold=0)
                    break

                except (ConnectionResetError, HTTPError, timeout) as e:
                    self.add_msg(e)
                    continue

            # get the comment authors and append
            # them to userList for scanning
            for comment in praw.helpers.flatten_tree(submission.comments):
                try:
                    commenter = str(comment.author)
                    comScore = int(comment.score)

                except AttributeError:
                    continue

                if comScore > self.minScore:
                    if commenter not in self.userList:
                        self.userList.append(commenter)
                        print("\r{0} users found up to thread ({1} / {2}).".format(len(self.userList), i + 1, self.scrapeLimit), end='')

        return self.userList


    def get_subs(self, userList):
        """
        This function uses the list collected by get_users()
        in order to find the crossover subreddits. It takes 1
        argument which is a list of users to scan through.
        It then stores the results in a list which will be
        put into tuples and then sorted. It returns a list of
        subreddits.
        """

        print("\nScanning for overlapping subreddits...")
        

        # keeps count on overlapping users
        self.counter = Counter()

        if not(os.path.isdir("users")):
            os.mkdir("users")

        # iterate through the list of users in order
        # to get their comments/submissions for crossreferencing
        for i, user in enumerate(userList):
            shadowbanned = False

            dbFile = "{0}.db".format(user)
            
            if not(os.path.isfile("users/{0}".format(dbFile))):
                while True:
                    try:
                        overview = self.client.get_redditor(user).get_overview(limit=self.overviewLimit)
                        break
                    # handle shadowbanned/deleted accounts
                    except (ConnectionResetError, HTTPError, timeout) as e:
                        if "404" in str(e):
                            shadowbanned = True
                            break

                        else:
                            self.add_msg('\n' + str(e))
                            continue

                if(shadowbanned):
                    continue

                con = db.connect("users/{0}".format(dbFile))
                cur = con.cursor()

                cur.execute("CREATE TABLE IF NOT EXISTS user(Overlap TEXT, Type TEXT, ID TEXT, Score INT)")

                # keeps track of user subs to prevent multiple
                # posts from being tallied
                self.userDone = []

                # keeps track of how many users are remaining
                usersLeft = len(userList) - i - 1

                print("\r({0} / {1}) users remaining.".format(usersLeft, len(userList)), end='')

                while True:
                    try:
                        for submission in overview:

                            try:
                                csubreddit = str(submission.subreddit)
                                comScore = int(submission.score)
                                comID = str(submission.id)

                            except AttributeError:
                                continue

                            try:
                                testIfSubmission = str(submission.stickied)
                                submissionType = "submission"

                            except AttributeError:
                                submissionType = "comment"

                            try:
                                cur.execute("INSERT INTO user VALUES(?, ?, ?, ?)", (csubreddit, submissionType, comID, comScore))

                            except OperationalError as e:
                                pass

                            if comScore > self.minScore:
                                if csubreddit not in self.userDone:
                                    # keep tabs on how many
                                    # users post to a subreddit
                                    self.counter[csubreddit] += 1
                                    self.userDone.append(csubreddit)

                                # add the ones that aren't kept in the list
                                # to the list of subreddits
                                if csubreddit not in self.subredditList:
                                    self.subredditList.append(csubreddit)

                        break

                    except (ConnectionResetError, HTTPError, timeout) as e:
                        self.add_msg('\n' + str(e))
                        continue

                con.commit()
                con.close()

            else:
                
                # keeps track of user subs to prevent multiple
                # posts from being tallied
                self.userDone = []

                # keeps track of how many users are remaining
                usersLeft = len(userList) - i - 1

                print("\r({0} / {1}) users remaining.".format(usersLeft, len(userList)), end='')

                con = db.connect("users/{0}".format(dbFile))
                cur = con.cursor()

                try:
                    cur.execute("SELECT * FROM user")

                except OperationalError as e:
                    con.close()
                    os.remove("users/{0}".format(dbFile))
                    continue

                for row in cur:
                    csubreddit = operator.getitem(row, 0)
                    comScore = int(operator.getitem(row, 3))

                    if comScore > self.minScore:
                        if csubreddit not in self.userDone:
                            self.counter[csubreddit] += 1
                            self.userDone.append(csubreddit)

                        if csubreddit not in self.subredditList:
                            self.subredditList.append(csubreddit)

                con.close()

        return self.subredditList


    def create_tuples(self, subreddit, subredditList):
        """
        This function takes 2 arguments, the first which
        is the subreddit that is being targeted for the drilldown.
        The second is the list of subreddits which will be put
        into tuples for storage. It returns a list of tuples that
        contains the subreddit and the overlapping users.
        """

        print("\nCreating tuples...")
        

        # stores the tuples to be used for printing data
        self.subredditTuple = []

        # create a bunch of tuples and adds them to a list
        # to neatly store the collected data for future sorting
        for item in subredditList:
            # avoids including posts made
            # in the selected subreddit
            # also exclude crossovers with less than 10 posters
            self.intCounter = int(self.counter[item])
            if item.lower() != subreddit.lower():
                if self.intCounter >= 5:
                    self.subredditTuple.append((item, self.intCounter))

        # sorts biggest to smallest by the 2nd tuple value
        # which is the post tally
        self.subredditTuple.sort(key=operator.itemgetter(1), reverse=True)

        return self.subredditTuple


    def add_db(self, subreddit, subredditTuple, userCount):
        """
        Iterates through a list of tuples which contain the name 
        of a subreddit and the amount of overlapping users. It takes 
        two arguments. The first is the subreddit which drilldown this 
        is for. The second is the collected list of tuples which 
        contain the overlapping subreddits and the amount of 
        overlapping users.
        """

        print("Adding data to database...")
        
        if not(os.path.isdir("subreddits")):
            os.mkdir("subreddits")

        dbFile = "{0}.db".format(subreddit)

        if(os.path.isfile("subreddits/{0}".format(dbFile))):
            pass

        else:

            # connect to the database file
            con = db.connect("subreddits/{0}".format(dbFile))
        
            # create the cursor object for the database
            cur = con.cursor()

            # make a table if it doesn't exist already
            cur.execute("CREATE TABLE IF NOT EXISTS drilldown(overlaps TEXT, users INT)")

            cur.execute("INSERT INTO drilldown VALUES(?, ?)", (subreddit, userCount))

            # store data from the tuples into the database
            for element in subredditTuple:
                subName = operator.getitem(element, 0)
                users = operator.getitem(element, 1)

                cur.execute("INSERT INTO drilldown VALUES(?, ?)", (subName, users))

            con.commit()
            con.close()


    def calculate_similarity(self, subreddit1, subreddit2):
        """
        Calculates the similarity between two subreddits. Give it the
        two subreddits to compare. Returns the similarity as a tuple 
        with subreddit2 as the first element and the similarity as 
        the second element.
        """

        print("Calculating similarity...")
        

        # format the file names
        dbFile1 = "{0}.db".format(subreddit1)
        dbFile2 = "{0}.db".format(subreddit2)

        # so these are defined in case that sub1 or sub2 don't 
        # show up in the drilldown for one of them they can be
        # set equal to each other so the program can calculate the
        # similarity between the 2 subsreddits.
        AB = None
        BA = None

        # if a drilldown for this subreddit hasn't been done then do it
        if(os.path.isfile("subreddits/{0}".format(dbFile1)) == False):
            while True:
                # get the list of users
                try:
                    userList = self.get_users(subreddit1)
                    self.userList = []
                    break

                except (InvalidSubreddit, RedirectException) as e:
                    self.add_msg(e)
                    logging.error(str(e) + "\n\n")
                    raise SkipThis("Skipping invalid subreddit...")

                except (APIException, ClientException, Exception) as e:
                    self.add_msg(e)
                    logging.error(str(e) + "\n\n")
                    raise SkipThis("Couldn't get users. Skipping...")
        
            while True:
                try:
                    # get the list of subreddits
                    subredditList = self.get_subs(userList)
                    self.subredditList = []
                    break

                except (APIException, ClientException, OperationalError) as e:
                        self.add_msg(e)
                        logging.error(str(e) + "\n\n")
                        raise SkipThis("Couldn't get overlapping subreddits. Skipping...")

                try:
                    # get the list of tuples
                    subredditTuple = self.create_tuples(subreddit1, subredditList)

                except Exception as e:
                    self.add_msg(e)
                    logging.error("Failed to create tuples. " + str(e) + "\n\n")
                    raise SkipThis("Failed to create tuples. Skipping...")

                try:
                    self.add_db(subreddit1, subredditTuple, len(userList))

                except Exception as e:
                    self.add_msg(e)
                    logging.error("Failed to add to database. " + str(e) + "\n\n")
                    raise SkipThis("Failed to add data to database. Skipping...")

        if(os.path.isfile("subreddits/{0}".format(dbFile2)) == False):
            if subreddit2 not in self.banList:
                while True:
                    # get the list of users
                    try:
                        userList = self.get_users(subreddit2)
                        self.userList = []
                        break

                    except (InvalidSubreddit, RedirectException) as e:
                        self.add_msg(e)
                        logging.error(str(e) + "\n\n")
                        raise SkipThis("Skipping invalid subreddit...")

                    except (APIException, ClientException, Exception) as e:
                        self.add_msg(e)
                        logging.error(str(e) + "\n\n")
                        raise SkipThis("Couldn't get users. Skipping...")
            
                while True:
                    try:
                        # get the list of subreddits
                        subredditList = self.get_subs(userList)
                        self.subredditList = []
                        break

                    except (APIException, ClientException, OperationalError) as e:
                        self.add_msg(e)
                        logging.error(str(e) + "\n\n")
                        raise SkipThis("Couldn't get overlapping subreddits. Skipping...")

                try:
                    # get the list of tuples
                    subredditTuple = self.create_tuples(subreddit2, subredditList)

                except Exception as e:
                    self.add_msg(e)
                    logging.error("Failed to create tuples. " + str(e) + "\n\n")
                    raise SkipThis("Failed to create tuples. Skipping...")

                try:
                    self.add_db(subreddit2, subredditTuple, len(userList))

                except Exception as e:
                    self.add_msg(e)
                    logging.error("Failed to add to database. " + str(e) + "\n\n")
                    raise SkipThis("Failed to add data to database. Skipping...")

            else:
                raise SkipThis("Subreddit in banlist. Skipping...")

        # Query statements need strings fed in tuples
        sub1 = (subreddit1,)
        sub2 = (subreddit2,)

        # open the database for subreddit 1
        con1 = db.connect("subreddits/{0}".format(dbFile1))
        cur1 = con1.cursor()

        # get the number of overlapping users from subreddit2
        cur1.execute("SELECT users FROM drilldown WHERE overlaps=?", sub2)

        for overlap in cur1:
            AB = operator.getitem(overlap, 0)

        # get the total number of users found in subreddit2
        cur1.execute("SELECT users FROM drilldown WHERE overlaps=?", sub1)

        for userCount in cur1:
            A = operator.getitem(userCount, 0)

        # close subreddit1's database file
        con1.close()

        # open the database for subreddit2
        con2 = db.connect("subreddits/{0}".format(dbFile2))
        cur2 = con2.cursor()

        # do the same thing for subreddit1 and was done for subreddit2
        cur2.execute("SELECT users FROM drilldown WHERE overlaps=?", sub1)

        for overlap in cur2:
            BA = operator.getitem(overlap, 0)

        if AB is None:
            AB = BA

        if BA is None:
            BA = AB

        cur2.execute("SELECT users FROM drilldown WHERE overlaps=?", sub2)

        for userCount in cur2:
            B = operator.getitem(userCount, 0)

        con2.close()

        try:
            # use the retrieved data to calculate similarity
            similarity = float("{0:.05f}".format((sqrt(AB * BA)) / (sqrt(float(A * B)))))

        except ZeroDivisionError:
            similarity = float(0.00000)

        except UnboundLocalError:
            raise SkipThis("Couldn't calculate similarity for this subreddit. Skipping...")
        
        return (subreddit2, similarity)


    def format_post(self, subreddit, userList):
        """
        This function formats the data in order to submit it to
        Reddit. It takes 3 arguments. The first is the subreddit
        that is being targeted for the drilldown. The second is
        the list of tuples for printing data. The last is the
        list of users in order to print the total amount of users
        discovered by the bot. It returns the formatted string.
        """

        print("Formatting post...")
        

        # similarity values will be stored here for sorting
        self.simList = []

        dbFile = "{0}.db".format(subreddit)

        con = db.connect("subreddits/{0}".format(dbFile))
        cur = con.cursor()

        self.bodyContent = ""

        # make a table
        self.bodyStart = "## /r/{0} Drilldown\n\n".format(subreddit)
        
        if(self.similarity):
            self.bodyStart += "| Subreddit | Similarity |\n"
            self.bodyStart += "|:------|------:|\n"

            cur.execute("SELECT * FROM drilldown")

            for row in cur:
                subreddit2 = operator.getitem(row, 0)

                if subreddit2 == subreddit:
                    continue

                if subreddit2 not in self.banList:

                    if len(self.simList) == self.similarityLimit:
                        break

                    try:
                        similarity = self.calculate_similarity(subreddit, subreddit2)
                        self.simList.append(similarity)

                    except SkipThis:
                        continue

            self.simList.sort(key=operator.itemgetter(1), reverse=True)

            # fill in the table
            for element in self.simList:
                sub = operator.getitem(element, 0)
                sim = operator.getitem(element, 1)
                self.bodyContent += "|/r/{0}|{1}|\n".format(sub, sim)

                if len(self.bodyStart + self.bodyContent) >= 1000:
                    break

        if type(userList) == list:
            userList = len(userList)

        self.bodyContent += "\nOf {0} Users Found:\n\n".format(userList)
        self.bodyContent += "| Subreddit | Overlapping users |\n"
        self.bodyContent += "|:------|------:|\n"

        cur.execute("SELECT * FROM drilldown")

        for row in cur:
            sub = operator.getitem(row, 0)

            if sub == subreddit:
                continue

            if sub not in self.banList:
                overlap = operator.getitem(row, 1)
                self.bodyContent += "|/r/{0}|{1}|\n".format(sub, overlap)

            if len(self.bodyStart + self.bodyContent) >= 14000:
                # so the drilldown doesn't get too big to post
                break

        text = self.bodyStart + self.bodyContent

        return text


    def submit_post(self, subreddit, text):
        """
        This function submits the results to Reddit. It takes
        two arguments. The first is the subreddit that was
        targeted for the drilldown. The second is the text for
        the submission thread.
        """

        print("Submitting post...")
        

        # post to this subreddit
        self.mySubreddit = self.client.get_subreddit(self.post_to)

        if(len(self.banList) > 0):
            # thread title
            title = "/r/{0} Drilldown {1}".format(subreddit, datetime.now().strftime("%B %Y"))

        else:
            title = "/r/{0} Drilldown {1} (Subreddit Bans Disabled)".format(subreddit, datetime.now().strftime("%B %Y"))

        # finally submit it
        return self.mySubreddit.submit(title, text)


    def give_flair(self, submission, flairText):
        """
        This post adds flair to the drilldown submission. Give 
        it the submission object and the flair text as a string.
        """

        if(self.setflair):
            self.add_msg("Setting post's flair...")
            while True:
                try:
                    self.client.set_flair(self.post_to, submission, flair_text=flairText)
                    break

                except (ConnectionResetError, HTTPError, timeout) as e:
                    self.add_msg(e)
                    continue

                except ModeratorRequired as e:
                    self.add_msg(e)
                    logging.error("Failed to set flair. " + str(e) + '\n' + str(submission.permalink) + "\n\n")
                    raise SkipThis("Could not assign flair. Moderator privileges are necessary.")
    

    def log_info(self, info):
        """
        This is for logging raw data in case you want to.
        """

        if(self.infoLogging):
            self.logDate = str(datetime.now().strftime("%Y-%m-%d"))
            self.logName = "SubredditAnalysis_{0}.txt".format(self.logDate)
            self.logFile = open(self.logName, 'a')

            self.logFile.write(str(info))

            self.logFile.close()


    def log_post(self, subreddit, post):
        """
        In the event that the bot can not submit a post to
        Reddit, this function will write that post to a text file
        so that your time isn't wasted. It takes 2 arguments: the
        drilldown subreddit and the post.
        """

        if(self.postLogging):
            self.logName = "{0}_results.txt".format(subreddit)
            self.postFile = open(self.logName, 'a')

            self.postFile.write(str(post))

            self.postFile.close()
