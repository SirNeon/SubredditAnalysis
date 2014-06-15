from collections import Counter
from datetime import datetime
import logging
import operator
import optparse
from sys import exit, stderr
from time import sleep
import praw
from praw.errors import *
from requests.exceptions import HTTPError


class SubredditAnalysis(object):


    def __init__(self):
        """
        Initialize the class with some basic attributes.
        """

        # add terminal output
        self.verbose = False

        # maximum threads to crawl. Reddit doesn't
        # like it when you go over 1000
        self.scrapeLimit = 1000

        # post drilldown to this subreddit
        self.post_to = "SubredditAnalysis"

        self.useragent = "Reddit Analysis Bot by /u/SirNeon"

        # optional logging
        self.infoLogging = False
        self.postLogging = False

        # I've banned defaults and former defaults since
        # there's bound to be overlap with those due to
        # how Reddit autosubscribes users to them
        self.banList = [
            "AdviceAnimals", "announcements", "Art", "atheism",
            "AskReddit", "askscience", "aww", "bestof",
            "blog", "books", "creepy", "dataisbeautiful",
            "DIY", "Documentaries", "EarthPorn",
            "explainlikeimfive", "Fitness", "food", "funny",
            "Futurology", "gadgets", "gaming", "GetMotivated",
            "gifs", "history", "IAmA", "InternetIsBeautiful",
            "Jokes", "LifeProTips", "listentothis",
            "mildlyinteresting", "movies", "Music", "news",
            "nosleep", "nottheonion", "OldSchoolCool",
            "personalfinance", "philosophy",
            "photoshopbattles", "pics", "politics", "science",
            "Showerthoughts", "space", "sports", "technology",
            "television", "tifu", "todayilearned",
            "TwoXChromosomes", "UpliftingNews", "videos",
            "worldnews", "WritingPrompts", "WTF"
        ]


    def add_msg(self, msg=None, newline=False):
        """
        Simple function to make terminal output optional. Feed
        it the message to print out. Can alsotell it to print a 
        newline if you want to.
        """

        if(self.verbose):
            if msg is not None:
                print msg

            if(newline):
                print '\n'


    def login(self, username, password):
        """
        This function logs the bot into its Reddit account.
        It takes 2 arguments: the username and the password.
        """

        self.client = praw.Reddit(user_agent=self.useragent)
        print "Logging in as {0}...".format(username)

        self.client.login(username, password)
        print "Login successful."


    def get_users(self, subreddit):
        """
        This function creates a list of users that posted in
        the subreddit which is being scanned. The data from these
        users is then collected to determine where else they post.
        It takes 1 argument, which is the subreddit to be scanned.
        It returns a list of users.
        """

        print "Getting users for /r/{0}...".format(subreddit)

        # get threads from the hot list
        submissions = self.client.get_subreddit(subreddit).get_hot(limit=self.scrapeLimit)

        # userbase in the selected subreddit to be scanned
        self.userList = []

        # get the thread creator and if he's not
        # in the userList then add him there
        for i, submission in enumerate(submissions):
            try:
                submitter = str(submission.author)

            except AttributeError:
                continue

            # make sure that users don't get added multiple times
            if submitter not in self.userList:
                self.userList.append(submitter)
                self.add_msg("{0} users found up to thread ({1} / {2}).".format(len(self.userList), i + 1, self.scrapeLimit))


            # load more comments
            submission.replace_more_comments(limit=None, threshold=0)

            # get the comment authors and append
            # them to userList for scanning
            for comment in praw.helpers.flatten_tree(submission.comments):
                try:
                    commenter = str(comment.author)

                except AttributeError:
                    continue

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

        print "Scanning for overlapping subreddits..."

        # list of overlapping subreddits
        subredditList = []

        # keeps count on overlapping users
        self.counter = Counter()

        # iterate through the list of users in order
        # to get their comments for crossreferencing
        for i, user in enumerate(userList):
            try:
                comments = self.client.get_redditor(user).get_comments('all')

            # handle shadowbanned/deleted accounts
            except HTTPError, e:
                self.add_msg(e)
                continue

            # keeps track of user subs to prevent multiple
            # posts from being tallied
            self.userDone = []

            # keeps track of how many users are remaining
            usersLeft = len(userList) - i - 1

            self.add_msg("({0} / {1}) users remaining.".format(usersLeft, len(userList)))

            for comment in comments:
                try:
                    csubreddit = str(comment.subreddit)

                except AttributeError:
                    continue

                if csubreddit not in self.userDone:
                    # keep tabs on how many
                    # users post to a subreddit
                    self.counter[csubreddit] += 1
                    self.userDone.append(csubreddit)

                # add the ones that aren't kept in the list
                # to the list of subreddits
                if csubreddit not in subredditList:
                    if csubreddit not in self.banList:
                        subredditList.append(csubreddit)

        return subredditList


    def create_tuples(self, subreddit, subredditList):
        """
        This function takes 2 arguments, the first which
        is the subreddit that is being targeted for the drilldown.
        The second is the list of subreddits which will be put
        into tuples for storage. It returns a list of tuples that
        contains the subreddit, the overlapping users, and their
        net karma.
        """

        print "Creating tuples..."

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


    def format_post(self, subreddit, subredditTuple, userList):
        """
        This function formats the data in order to submit it to
        Reddit. It takes 3 arguments. The first is the subreddit
        that is being targeted for the drilldown. The second is
        the list of tuples for printing data. The last is the
        list of users in order to print the total amount of users
        discovered by the bot. It returns the formatted string.
        """

        print "Formatting post..."

        # make a table
        self.bodyStart = "## /r/{0} Drilldown\n\n".format(subreddit)
        self.bodyStart += "Of {0} Users Found:\n\n".format(len(userList))
        self.bodyStart += "| Subreddit | Overlapping users |\n"
        self.bodyStart += "|:------|------:|\n"

        self.bodyContent = ""

        # fill in the table
        for i in range(0, len(subredditTuple)):
            sub = "".join(subredditTuple[i][0])
            overlap = "".join(str(subredditTuple[i][1]))
            self.bodyContent += "|/r/{0}|{1}|\n".format(sub, overlap)

            if len(self.bodyStart + self.bodyContent) >= 9900:
                # so the table doesn't get too big to post
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

        print "Submitting post..."

        # post to this subreddit
        self.mySubreddit = self.client.get_subreddit(self.post_to)

        # thread title
        title = "/r/{0} Drilldown {1}".format(subreddit, datetime.now().strftime("%B %Y"))

        # finally submit it
        return self.mySubreddit.submit(title, text)
    

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


class skipThis(Exception):
    pass


def login(username, password):
    for i in range(0, 3):
        try:
            myBot.login(username, password)
            break

        except (InvalidUser, InvalidUserPass, RateLimitExceeded, APIException) as e:
                print e
                logging.debug(str(e) + "\n\n")
                exit(1)

        except HTTPError, e:
            myBot.add_msg(e)
            logging.debug(str(e) + "\n\n")
            
            if i == 2:
                print "Failed to login."
                exit(1)
            
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

                print "Verifying /r/{0}...".format(subreddit)

                try:
                    # make sure the subreddit is valid
                    testSubmission = myBot.client.get_subreddit(subreddit).get_new(limit=1)
                    for submission in testSubmission:
                        "".join(submission.title)

                except (InvalidSubreddit, RedirectException) as e:
                    myBot.add_msg(e)
                    logging.debug("Invalid subreddit. Removing from list." + str(e) + "\n\n")
                    subredditList.remove(subreddit)
                    raise skipThis

                except HTTPError, e:
                    myBot.add_msg(e)
                    logging.debug(str(subreddit) + ' ' + str(e) + "\n\n")

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
                    raise skipThis

                except (APIException, ClientException, Exception) as e:
                    myBot.add_msg(e)
                    logging.debug(str(e) + "\n\n")

                    if str(e) == "timed out":
                        myBot.add_msg("Waiting to try again...")
                        sleep(60)
                        continue

                    else:
                        raise skipThis

            break

        except skipThis:
            if i == 2:
                print "Couldn't verify the validity of the listed subreddits. Quitting..."
                exit(1)

            else:
                continue

    # keeps this message from being displayed when
    # the only item is a quit command
    if subredditList[0] not in ["quit", ".quit", 'q']:
        print "Subreddit verification completed."


def main():
    
    # login credentials
    # these can be overwritten with commandline arguments
    username = ""
    password = ""

    
    # commandline options for additional feature support
    parser = optparse.OptionParser("python redditanalysisbot.py [options]")
    parser.add_option("--aB", "--addBan", dest="tgtBan", type="string", help="Add a subreddit to the ban list. Separate subreddits with commas.")
    parser.add_option("--aL", "--enableLogging", dest="enableLogging", type="string", help="Turn all logging on or off. On by default.")
    parser.add_option("-b", "--banList", dest="banOption", type="string", help="Turn the ban list on and off. On by default.")
    parser.add_option("--iL", "--infoLogging", dest="infoLogging", type="string", help="Turn raw data logging on and off. On by default.")
    parser.add_option("-p", "--postHere", dest="SubredditName", type="string", help="Post to this subreddit. Defaults to /r/SubredditAnalysis")
    parser.add_option("--pL", "--postLogging", dest="postLogging", type="string", help="Turn post logging on and off. On by default.")
    parser.add_option("-s", "--scrapeLimit", dest="ScrapeLimit", type="int", help="Set the number of submissions to be scanned. 1000 by default.")
    parser.add_option("-v", "--verbose", dest="verbosity", type="string", help="Make the program more verbose with status updates and print out errors. Defaults to off.")
    parser.add_option("-u", "--userCreds", dest="userCreds", type="string", help="Give the bot the username and password for a Reddit account. Separate them with a comma.")
    parser.add_option("--uB", "--unBan", dest="tgtUnban", type="string", help="Remove a subreddit from the ban list. Separate subreddits with commas.")
    (options, args) = parser.parse_args()

    if options.enableLogging is not None:
        if options.enableLogging.lower() == "on":
            myBot.infoLogging = True
            myBot.postLogging = True

        elif options.enableLogging.lower() == "off":
            myBot.infoLogging = False
            myBot.postLogging = False

        else:
            print "Invalid argument for logging. Use either \"on\" or \"off\"."
            exit(1)

    if options.banOption is not None:
        if options.banOption.lower() == "on":
            pass

        elif options.banOption.lower() == "off":
            myBot.banList = []

        else:
            print "Invalid argument for logging. Use either \"on\" or \"off\"."
            exit(1)

    if options.infoLogging is not None:
        if options.infoLogging.lower() == "on":
            myBot.infoLogging = True

        elif options.infoLogging.lower() == "off":
            myBot.infoLogging = False

        else:
            print "Invalid agument for logging. Use either \"on\" or \"off\"."
            exit(1)

    if options.postLogging is not None:
        if options.postLogging.lower() == "on":
            myBot.postLogging = True

        elif options.postLogging.lower() == "off":
            myBot.postLogging = False

        else:
            print "Invalid argument for logging. Use either \"on\" or \"off\"."
            exit(1)

    if options.ScrapeLimit is not None:
        myBot.scrapeLimit = options.ScrapeLimit

    if options.verbosity is not None:
        if options.verbosity.lower() == "on":
            myBot.verbose = True

        elif options.verbosity.lower() == "off":
            myBot.verbose = False

        else:
            print "Invalid argument for verbosity. Use either \"on\" or \"off\"."
            exit(1)

    if options.userCreds is not None:
        credentials = options.userCreds.split(',')
        username = credentials[0]
        password = credentials[1]

    print "Welcome to Reddit Analysis Bot."

    print "Type \"quit\", \".quit\", or \'q\' to exit the program."

    login(username, password)

    # these 3 require the client attribute, which is created
    # in the login function
    if options.tgtBan is not None:
        checkList = options.tgtBan.split(',')

        check_subreddits(checkList)

        for element in checkList:
            myBot.banList.append(element)

    if options.SubredditName is not None:
        checkList = [options.SubredditName]

        check_subreddits(checkList)

        if checkList == []:
            print "Subreddit failed check. Can't post there."
            exit(1)

        else:
            myBot.post_to = options.SubredditName

    if options.tgtUnban is not None:
        checkList = options.tgtUnban.split(',')

        check_subreddits(checkList)

        for element in checkList:
            myBot.banList.remove(element)

    while True:
        # list of subreddits you want to analyze
        drilldownList = raw_input("Enter the subreddits you wish to target.~/> ").split()

        # check to make sure each subreddit is valid
        check_subreddits(drilldownList)

        # iterate through the drilldownList to get data
        for subreddit in drilldownList:

            if(subreddit in ["quit", ".quit", 'q']):
                print "Quitting..."
                exit(0)

            else:
                try:
                    while True:
                        # get the list of users
                        try:
                            userList = myBot.get_users(subreddit)
                            break

                        except (InvalidSubreddit, RedirectException) as e:
                            myBot.add_msg(e)
                            logging.debug("Invalid subreddit. Removing from list." + str(e) + "\n\n")
                            drilldownList.remove(subreddit)
                            raise skipThis

                        except HTTPError, e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")

                            if str(e) == "timed out":
                                myBot.add_msg("Waiting to try again...")
                                sleep(60)
                                continue

                            else:
                                raise skipThis

                except skipThis:
                    print "Couldn't get user list. Skipping..."
                    continue

                for user in userList:
                    myBot.log_info(user + ',')

                myBot.log_info("\n\n")


                try:
                    while True:
                        try:
                            # get the list of subreddits
                            subredditList = myBot.get_subs(userList)
                            break

                        except HTTPError, e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")

                            if str(e) == "timed out":
                                myBot.add_msg("Waiting a minute to try again.")
                                sleep(60)
                                continue

                            else:
                                raise skipThis

                except skipThis:
                    print "Couldn't get subreddit list. Skipping..."
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

                    # format the data for Reddit
                    text = myBot.format_post(subreddit, subredditTuple, userList)

                except Exception, e:
                    myBot.add_msg(e)
                    logging.debug("Failed to create tuples. " + str(e) + "\n\n")
                    continue

                try:
                    while True:
                        try:
                            # submit the post for Reddit
                            post = myBot.submit_post(subreddit, text)
                            break

                        except HTTPError, e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.debug(str(e) + "\n\n")

                            if str(e) == "timed out":
                                myBot.add_msg("Waiting to try again...")
                                sleep(60)
                                continue

                            else:
                                raise skipThis

                except skipThis:
                    print "Couldn't submit post. Skipping..."
                    logging.debug(str(e) + "\n\n")
                    myBot.log_post(subreddit, text)
                    continue

                if(post != None):
                    try:
                        for i in range(0, 3):
                            # this requires mod privileges
                            try:
                                print "Setting post's flair..."
                                myBot.client.set_flair(myBot.post_to, post, flair_text=subreddit)
                                break

                            except ModeratorRequired, e:
                                myBot.add_msg(e)
                                logging.debug("Failed to set flair. " + str(e) + '\n' + str(submission.permalink) + "\n\n")
                                raise skipThis

                            except HTTPError, e:
                                myBot.add_msg(e)
                                logging.debug(str(e) + "\n\n")
                                myBot.add_msg("Waiting to try again...")
                                sleep(60)
                                continue

                            except (APIException, ClientException, Exception) as e:
                                myBot.add_msg(e)
                                logging.debug(str(e) + "\n\n")

                                if str(e) == "timed out":
                                    myBot.add_msg("Waiting to try again...")
                                    sleep(60)
                                    continue

                                else:
                                    raise skipThis

                    except skipThis:
                        print "Couldn't assign flair. Skipping..."
                        continue


if __name__ == "__main__":
    myBot = SubredditAnalysis()

    # comment this out if you want minimal terminal output
    myBot.verbose = True

    # comment these out if you don't want logging
    myBot.infoLogging = True
    errorLogging = True
    myBot.postLogging = True

    if(errorLogging):
        logging.basicConfig(
            filename="SubredditAnalysis_logerr.log", 
            filemode='a', format="%(asctime)s\nIn "
            "%(filename)s (%(funcName)s:%(lineno)s): "
            "%(message)s", datefmt="%Y-%m-%d %H:%M:%S", 
            level=logging.DEBUG, stream=stderr
        )

    main()
