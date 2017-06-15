require 'yaml'
require 'NeonRAW'
require_relative 'databasemanager'
require_relative 'redditdatamanager'

# The actual crawler that you use to do stuff.
class SubredditAnalysis
  include NeonRAW::Errors

  class << self
    public :define_method
  end

  include DatabaseManager
  include RedditDataManager

  def initialize
    if File.file?('settings.yaml')
      @config = YAML.load_file('settings.yaml')
    else
      raise('Could not find settings.yaml. Exiting...')
    end
    @verbose = @config['verbose']
    @info_logging = @config['info_logging']
    @post_logging = @config['post_logging']
    @error_logging = @config['error_logging']
  end

  # Prints progress information and errors to the terminal if verbosity
  # is turned on in the settings.yaml file.
  # @!method add_msg(msg = nil, opts = { newline: true })
  # @param msg [String] The message to print.
  # @param opts [Hash] Hash that contains optional parameters.
  # @option opts :newline [Boolean] Decides whether or not to add an extra
  #   newline.
  def add_msg(msg = nil, opts = { newline: true })
    print msg if @verbose && !msg.nil?
    print "\n" if opts[:newline]
  end

  # Creates the banlist by reading through the banlist.txt file.
  # @!method create_banlist
  # @return [Array] Returns an array full of strings containing the subreddits
  #   to be ignored by the analysis bot if it is enabled in the settings.yaml
  #   file.
  def create_banlist
    banlist_is_desired = @config['banlist']
    ban_list = []
    if banlist_is_desired && File.file?('banlist.txt')
      File.open('banlist.txt', 'r').each { |line| ban_list << line.chomp }
    end
    ban_list
  end

  # Initializes the Redd.it client and creates a Reddit session.
  # @!method login
  def login
    @client = NeonRAW.script(
      @config['username'],
      @config['password'],
      @config['client_id'],
      @config['secret'],
      user_agent: 'Reddit Analysis Crawler by /u/SirNeon'
    )
  end
end
