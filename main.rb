# rubocop:disable Style/GlobalVars

require 'NeonRAW'
require_relative 'lib/crawler'
include NeonRAW::Errors

def login
  $my_bot.add_msg('Logging in...')
  loop do
    begin
      $my_bot.login
      $my_bot.add_msg('Login successful.')
      break
    rescue InvalidCredentials, InvalidOAuth2Credentials => error
      abort(error.message)
    rescue CouldntReachServer, InternalServerError, ServiceUnavailable
      sleep(5)
      redo
    end
  end
end

def check_subreddits(subreddit_list)
  subreddit_list.each do |subreddit|
    begin
      $my_bot.get_submissions(subreddit, limit: 1)
    rescue PermissionDenied => error # subreddit is private
      $my_bot.add_msg(subreddit + ' ' + error)
      subreddit_list.delete(subreddit)
      next
    rescue NotFound => error # subreddit is banned/doesn't exist
      $my_bot.add_msg(subreddit + ' ' + error)
      subreddit_list.delete(subreddit)
      next
    rescue CouldntReachServer, InternalServerError, ServiceUnavailable
      sleep(5)
      redo
    end
  end
end

def fill_up_userlist(subreddit)
  submissions = $my_bot.get_submissions(subreddit)
  users = []
  submissions.each_with_index do |submission, i|
    $my_bot.add_msg(
      "Working on submission #{i + 1} / #{submissions.length}...\r",
      newline: false
    )
    $my_bot.get_users(users, submission)
  end
  users
end

def prepare_userlist(user_list)
  user_list.uniq!
  user_list.delete('[deleted]') if user_list.include?('[deleted]')
end

def tally_data(subreddit, user_list)
  overlap_tally = Hash.new(0)
  user = $my_bot.fetch_user_from_queue
  i = 0
  until user.empty?
    $my_bot.add_msg("Working on user #{i + 1} / #{user_list.length}...\r",
                    newline: false)
    data = $my_bot.fetch_users_data(user)
    i += 1
    if data.empty?
      overview = $my_bot.get_overview(user)
      next if overview.nil?
      user_data = $my_bot.gather_user_data(overview)
      $my_bot.tally_user_data(user, user_data, overlap_tally)
    else
      $my_bot.tally_user_data(user, data, overlap_tally)
    end
    user = $my_bot.fetch_user_from_queue
  end
  overlap_tally.delete(subreddit) if overlap_tally.include?(subreddit)
  overlap_tally
end

def sort_data(data)
  # sort by overlapping users highest to lowest
  data.sort_by { |_k, v| v }.reverse.to_h
end

def quit
  puts 'Exiting...'
  exit
end

def start(subreddit)
  $my_bot.add_msg("Working on #{subreddit}...")
  sub_data = $my_bot.fetch_subreddits_data(subreddit)
  return sub_data unless sub_data.empty?

  users = fill_up_userlist(subreddit)
  $my_bot.add_msg # clean out stdout
  prepare_userlist(users)
  $my_bot.write_users_to_queue(users)
  overlap_tally = tally_data(subreddit, users)
  subreddit_data = sort_data(overlap_tally)
  $my_bot.add_msg

  $my_bot.write_to_subreddits_db(subreddit, subreddit_data)
  $my_bot.clean_up
  subreddit_data
end

def main
  loop do
    print 'Input the subreddits you wish to target separated by spaces:~> '
    subreddit_list = gets.chomp.split(' ')
    quit if %w(quit q).include?(subreddit_list.first)
    login
    check_subreddits(subreddit_list)
    $my_bot.create_tables

    subreddit_list.each do |subreddit|
      data = start(subreddit)
    end
  end
end

puts "Welcome to RedditAnalysisBot. Input 'quit' or 'q' to quit."
$my_bot = SubredditAnalysis.new
main
