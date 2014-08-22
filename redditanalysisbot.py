from collections import Counter
from datetime import datetime
import logging
from math import sqrt
import operator
import os
import sqlite3 as db
from socket import timeout
import sys
from time import sleep
import praw
from praw.errors import *
from requests.exceptions import HTTPError
from simpleconfigparser import simpleconfigparser


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

            except (HTTPError, timeout) as e:
                self.add_msg(e)
                continue
        
        # get the thread creator and if he's not
        # in the userList then add him there
        for i, submission in enumerate(submissions):
            if len(self.userList) > 10000:
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
                    self.add_msg("{0} users found up to thread ({1} / {2}).".format(len(self.userList), i + 1, self.scrapeLimit))


            while True:
                try:
                    # load more comments
                    submission.replace_more_comments(limit=None, threshold=0)
                    break

                except (HTTPError, timeout) as e:
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
                        self.add_msg("{0} users found up to thread ({1} / {2}).".format(len(self.userList), i + 1, self.scrapeLimit))

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

        print("Scanning for overlapping subreddits...")
        

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
                con = db.connect("users/{0}".format(dbFile))
                cur = con.cursor()

                while True:
                    try:
                        overview = self.client.get_redditor(user).get_overview(limit=self.overviewLimit)
                        break
                    # handle shadowbanned/deleted accounts
                    except (HTTPError, timeout) as e:
                        self.add_msg(e)

                        if "404" in str(e):
                            shadowbanned = True
                            break

                        else:
                            continue

                if(shadowbanned):
                    continue

                cur.execute("CREATE TABLE IF NOT EXISTS user(Overlap TEXT, Type TEXT, ID TEXT, Score INT)")

                # keeps track of user subs to prevent multiple
                # posts from being tallied
                self.userDone = []

                # keeps track of how many users are remaining
                usersLeft = len(userList) - i - 1

                self.add_msg("({0} / {1}) users remaining.".format(usersLeft, len(userList)))

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

                            cur.execute("INSERT INTO user VALUES(?, ?, ?, ?)", (csubreddit, submissionType, comID, comScore))

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

                    except (HTTPError, timeout) as e:
                        self.add_msg(e)
                        continue

            else:
                
                # keeps track of user subs to prevent multiple
                # posts from being tallied
                self.userDone = []

                # keeps track of how many users are remaining
                usersLeft = len(userList) - i - 1

                self.add_msg("({0} / {1}) users remaining.".format(usersLeft, len(userList)))

                con = db.connect("users/{0}".format(dbFile))
                cur = con.cursor()

                cur.execute("SELECT * FROM user")

                for row in cur:
                    csubreddit = operator.getitem(row, 0)
                    comScore = int(operator.getitem(row, 3))

                    if comScore > self.minScore:
                        if csubreddit not in self.userDone:
                            self.counter[csubreddit] += 1
                            self.userDone.append(csubreddit)

                        if csubreddit not in self.subredditList:
                            self.subredditList.append(csubreddit)

        return self.subredditList


    def create_tuples(self, subreddit, subredditList):
        """
        This function takes 2 arguments, the first which
        is the subreddit that is being targeted for the drilldown.
        The second is the list of subreddits which will be put
        into tuples for storage. It returns a list of tuples that
        contains the subreddit and the overlapping users.
        """

        print("Creating tuples...")
        

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
                try:
                    userList = self.get_users(subreddit1)
                    self.userList = []
                    break

                except (APIException, ClientException, Exception) as e:
                    self.add_msg(e)
                    continue
            
            while True:
                try:
                    subredditList = self.get_subs(userList)
                    self.subredditList = []
                    break

                except (APIException, ClientException, Exception) as e:
                    self.add_msg(e)
                    continue

            while True:
                try:
                    subredditTuple = self.create_tuples(subreddit1, subredditList)
                    self.subredditTuple = []
                    break

                except (APIException, ClientException, Exception) as e:
                    self.add_msg(e)
                    continue

            self.add_db(subreddit1, subredditTuple, len(userList))

        if(os.path.isfile("subreddits/{0}".format(dbFile2)) == False):
            if subreddit2 not in self.banList:
                while True:
                    try:
                        userList = self.get_users(subreddit2)
                        self.userList = []
                        break

                    except (APIException, ClientException, Exception) as e:
                        self.add_msg(e)
                        continue

                while True:
                    try:
                        subredditList = self.get_subs(userList)
                        self.subredditList = []
                        break

                    except (APIException, ClientException, Exception) as e:
                        self.add_msg(e)
                        continue
                
                while True:
                    try:
                        subredditTuple = self.create_tuples(subreddit2, subredditList)
                        self.subredditTuple = []
                        break

                    except HTTPError as e:
                        self.add_msg(e)

                self.add_db(subreddit2, subredditTuple, len(userList))

            else:
                raise skipThis("Subreddit in banlist. Skipping...")

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

        # use the retrieved data to calculate similarity
        similarity = "{0:.05f}".format((sqrt(AB * BA)) / (sqrt(float(A * B))))
        
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

                    if len(self.simList) == 200:
                        break

                    similarity = self.calculate_similarity(subreddit, subreddit2)
                    self.simList.append(similarity)

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
            while True:
                try:
                    self.add_msg("Setting post's flair...")
                    self.client.set_flair(self.post_to, submission, flair_text=flairText)
                    break

                except (HTTPError, timeout) as e:
                    self.add_msg(e)
                    continue

                except ModeratorRequired as e:
                    self.add_msg(e)
                    logging.error("Failed to set flair. " + str(e) + '\n' + str(submission.permalink) + "\n\n")
                    raise skipThis("Could not assign flair. Moderator privileges are necessary.")
    

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


class SettingsError(Exception):
    

    def __init__(self, error):
        print(error)


class skipThis(Exception):
    

    def __init__(self, error):
        print(error)


def login(username, password):
    for i in range(0, 3):
        try:
            myBot.login(username, password)
            break

        except (InvalidUser, InvalidUserPass, RateLimitExceeded, APIException) as e:
                myBot.add_msg(e)
                logging.error(str(e) + "\n\n")
                sys.exit(1)

        except (HTTPError, timeout) as e:
            myBot.add_msg(e)
            logging.error(str(e) + "\n\n")
            
            if i == 2:
                print("Failed to login.")
                sys.exit(1)
            
            else:
                # wait a minute and try again
                sleep(60)
                continue


def check_subreddits(subredditList):
    """
    Checks on the listed subreddits to make sure that they are 
    valid subreddits and that there's no typos and whatnot. This 
    function removes the bad subreddits from the list so the bot 
    can carry on with its task. Feed it the list of subreddits.
    """

    for i in range(0, 3):
        try:
            for subreddit in subredditList:
                if(subreddit in ["quit", ".quit", 'q']):
                    continue

                print("Verifying /r/{0}...".format(subreddit))
                

                try:
                    # make sure the subreddit is valid
                    testSubmission = myBot.client.get_subreddit(subreddit).get_new(limit=1)
                    for submission in testSubmission:
                        "".join(submission.title)

                except (InvalidSubreddit, RedirectException) as e:
                    myBot.add_msg(e)
                    logging.error("Invalid subreddit. Removing from list." + str(e) + "\n\n")
                    subredditList.remove(subreddit)
                    raise skipThis("Skipping invalid subreddit...")

                except (HTTPError, timeout) as e:
                    myBot.add_msg(e)
                    logging.error(str(subreddit) + ' ' + str(e) + "\n\n")

                    # private subreddits return a 403 error
                    if "403" in str(e):
                        myBot.add_msg("/r/{0} is private. Removing from list...".format(subreddit))
                        subredditList.remove(subreddit)
                        continue

                    # banned subreddits return a 404 error
                    if "404" in str(e):
                        myBot.add_msg("/r/{0} banned. Removing from list...".format(subreddit))
                        subredditList.remove(subreddit)
                        continue

                    myBot.add_msg("Waiting a minute to try again...")   
                    sleep(60)
                    raise skipThis("Trying again...")

                except (APIException, ClientException, Exception) as e:
                    myBot.add_msg(e)
                    logging.error(str(e) + "\n\n")
                    raise skipThis("Something went wrong. Skipping...")

            break

        except skipThis:
            if i == 2:
                sys.exit(1)

            else:
                continue

    try:
        # keeps this message from being displayed when
        # the only item is a quit command
        if subredditList[0] not in ["quit", ".quit", 'q']:
            print("Subreddit verification completed.")

    except IndexError:
        print("Subreddit List empty.")
        

def main():
    
    # login credentials
    username = myBot.config.login.username
    password = myBot.config.login.password

    print("Welcome to Reddit Analysis Bot.")
    print("Type \"quit\", \".quit\", or \'q\' to exit the program.")
    
    login(username, password)

    while True:
        try:
            # list of subreddits you want to analyze
            drilldownList = raw_input("Enter the subreddits you wish to target.~/> ").split()

        except NameError:
            # python 3 support
            drilldownList = input("Enter the subreddits you wish to target.~/> ").split()

        # check to make sure each subreddit is valid
        check_subreddits(drilldownList)

        # iterate through the drilldownList to get data
        for subreddit in drilldownList:

            # check to see if a drilldown for this subreddit
            # was already done
            dbFile = "{0}.db".format(subreddit)

            if(subreddit in ["quit", ".quit", 'q']):
                print("Quitting...")
                
                sys.exit(0)

            elif(os.path.isfile("subreddits/{0}".format(dbFile))):
                con = db.connect("subreddits/{0}".format(dbFile))
                cur = con.cursor()

                sub = (subreddit,)

                cur.execute("SELECT users FROM drilldown WHERE overlaps=?", sub)

                for element in cur:
                    userList = operator.getitem(element, 0)

                try:
                    # format the data for Reddit
                    text = myBot.format_post(subreddit, userList)
                
                except Exception as e:
                    myBot.add_msg(e)
                    logging.error("Failed to format post. " + str(e) + "\n\n")
                    continue

                try:
                    while True:
                        try:
                            # submit the post for Reddit
                            post = myBot.submit_post(subreddit, text)
                            break

                        except (HTTPError, timeout) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Something went wrong. Skipping...")

                except skipThis:
                    logging.error(str(e) + "\n\n")
                    myBot.log_post(subreddit, text)
                    continue

                if(post != None):
                    try:

                        try:
                            myBot.give_flair(post, subreddit)

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Couldn't flair post. Skipping...")

                    except skipThis:
                        continue

                con.close()
                continue

            else:
                try:
                    while True:
                        # get the list of users
                        try:
                            userList = myBot.get_users(subreddit)
                            myBot.userList = []
                            break

                        except (InvalidSubreddit, RedirectException) as e:
                            myBot.add_msg(e)
                            logging.error("Invalid subreddit. Removing from list." + str(e) + "\n\n")
                            drilldownList.remove(subreddit)
                            raise skipThis("Skipping invalid subreddit...")

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Couldn't get users. Skipping...")

                except skipThis:
                    continue

                for user in userList:
                    myBot.log_info(user + ',')

                myBot.log_info("\n\n")


                try:
                    while True:
                        try:
                            # get the list of subreddits
                            subredditList = myBot.get_subs(userList)
                            myBot.subredditList = []
                            break

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Couldn't get overlapping subreddits. Skipping...")

                except skipThis:
                    continue

                for sub in subredditList:
                    myBot.log_info(sub + ',')

                myBot.log_info("\n\n")


                try:
                    # get the list of tuples
                    subredditTuple = myBot.create_tuples(subreddit, subredditList)

                    for item in subredditTuple:
                        myBot.log_info(item)
                        myBot.log_info(',')

                    myBot.log_info("\n\n")

                except Exception as e:
                    myBot.add_msg(e)
                    logging.error("Failed to create tuples. " + str(e) + "\n\n")
                    continue

                try:
                    myBot.add_db(subreddit, subredditTuple, len(userList))

                except Exception as e:
                    myBot.add_msg(e)
                    logging.error("Failed to add to database. " + str(e) + "\n\n")
                    continue

                try:
                    # format the data for Reddit
                    text = myBot.format_post(subreddit, userList)
                
                except Exception as e:
                    myBot.add_msg(e)
                    logging.error("Failed to format post. " + str(e) + "\n\n")
                    continue


                try:
                    while True:
                        try:
                            # submit the post for Reddit
                            post = myBot.submit_post(subreddit, text)
                            break

                        except (HTTPError, timeout) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Couldn't submit post. Skipping...")

                except skipThis:
                    logging.error(str(e) + "\n\n")
                    myBot.log_post(subreddit, text)
                    continue

                if(post != None):
                    try:
                        try:
                            print("Setting post's flair...")
                            
                            myBot.give_flair(post, subreddit)

                        except ModeratorRequired as e:
                            myBot.add_msg(e)
                            logging.error("Failed to set flair. " + str(e) + '\n' + str(post.permalink) + "\n\n")
                            raise skipThis("Need moderator privileges to set flair. Skipping...")

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise skipThis("Couldn't set flair. Skipping...")

                    except skipThis:
                        continue


if __name__ == "__main__":
    myBot = SubredditAnalysis()

    if(myBot.errorLogging):
        logging.basicConfig(
            filename="SubredditAnalysis_logerr.log", 
            filemode='a', format="%(asctime)s\nIn "
            "%(filename)s (%(funcName)s:%(lineno)s): "
            "%(message)s", datefmt="%Y-%m-%d %H:%M:%S", 
            level=logging.ERROR
        )

    main()
