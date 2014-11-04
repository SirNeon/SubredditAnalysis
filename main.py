import logging
import operator
import os
import sqlite3 as db
from sqlite3 import OperationalError
from socket import timeout
import sys
from time import sleep
from praw.errors import *
from requests.exceptions import HTTPError
from crawler import SubredditAnalysis
from exceptions import *


def login(username, password):
    for i in range(0, 3):
        try:
            myBot.login(username, password)
            break

        except (InvalidUser, InvalidUserPass, RateLimitExceeded, APIException) as e:
                myBot.add_msg(e)
                logging.error(str(e) + "\n\n")
                sys.exit(1)

        except (ConnectionResetError, HTTPError, timeout) as e:
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
                    raise SkipThis("Skipping invalid subreddit...")

                except (ConnectionResetError, HTTPError, timeout) as e:
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
                    raise SkipThis("Trying again...")

                except (APIException, ClientException, Exception) as e:
                    myBot.add_msg(e)
                    logging.error(str(e) + "\n\n")
                    raise SkipThis("Something went wrong. Skipping...")

            break

        except SkipThis:
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

                        except (ConnectionResetError, HTTPError, timeout) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise SkipThis("Something went wrong. Skipping...")

                except SkipThis:
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
                            raise SkipThis("Couldn't flair post. Skipping...")

                    except SkipThis:
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
                            raise SkipThis("Skipping invalid subreddit...")

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise SkipThis("Couldn't get users. Skipping...")

                except SkipThis:
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

                        except (APIException, ClientException, OperationalError) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise SkipThis("Couldn't get overlapping subreddits. Skipping...")

                except SkipThis:
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

                        except (ConnectionResetError, HTTPError, timeout) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            myBot.add_msg("Waiting to try again...")
                            sleep(60)
                            continue

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise SkipThis("Couldn't submit post. Skipping...")

                except SkipThis:
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
                            raise SkipThis("Need moderator privileges to set flair. Skipping...")

                        except (APIException, ClientException, Exception) as e:
                            myBot.add_msg(e)
                            logging.error(str(e) + "\n\n")
                            raise SkipThis("Couldn't set flair. Skipping...")

                    except SkipThis:
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
