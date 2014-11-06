try:
	from setuptools import setup
except ImportError:
	from distutils.core import setup

config = {
	'description': 'Source code for /u/RedditAnalysisBot',
	'author': '/u/SirNeon',
	'url': 'https://github.com/SirNeon618/SubredditAnalysis',
	'download_url': 'https://github.com/SirNeon618/SubredditAnalysis/archive/1.0.zip',
	'version': '1.0',
	'install_requires': ['praw', 'requests', 'simpleconfigparser'],
	'packages': [],
	'scripts': [],
	'name': 'SubredditAnalysis'
}

setup(**config)
