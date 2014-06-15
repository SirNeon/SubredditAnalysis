SubredditAnalysis
=================

**For maintaining the source code of /u/RedditAnalysisBot**

Requirements
------------
* Python 2.7
* Praw
* Requests

###Install Dependencies
In order to run the bot, you must install some necessary packages. To do so, run this command:

    pip install requirements.txt
    
Commandline Flags
-----------------

* **--aB (--addBan)** *Subreddit1,Subreddit2,...* **- Adds subreddits to the list of banned subreddits.**

* **--aL (--enableLogging)** *on|off* **- Turns logging on or off. Off by default.**

* **-b (--banList)** *on|off* **- Turns the banList on or off. On by default.**

* **--iL (--infoLogging)** *on|off* **- Turns raw data logging on or off. Off by default.**

* **-p (--postHere)** *SubredditName* **(don't include "/r/") - Posts the results to this subreddit. Defaults to /r/SubredditAnalysis.** 

* **--pL (--postLogging)** *on|off* **- Turns post logging on or off. Off by default.**

* **-s (--scrapeLimit)** *integer* **- Set the number of submissions to crawl. Defaults to and maxes at 1000.**

* **-v (--verbosity)** *on|off* **- Turn off extra terminal messages. Off by default.**

* **-u (--userCreds)** *username,password* **- Log the bot into this Reddit account.**

* **--uB (--unBan)** *Subreddit1,Subreddit2,...* **- Removes subreddits from the list of banned subreddits.**
