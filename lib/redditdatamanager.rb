# RedditDataManager handles everything that involves getting data from Reddit
# and inspecting said data.
module RedditDataManager
  # Grabs submissions from a subreddit.
  # @!method get_submissions(subreddit)
  # @param subreddit [String] The subreddit to get the submissions from.
  # @param opts [Hash] The hash table containing optional parameters.
  # @option opts [Integer] :limit The number of submissions to fetch.
  # @return [NeonRAW::Objects::Listing] Returns the scraped submissions.
  def get_submissions(subreddit, opts = {})
    reddit_exception_handling do
      scrape_limit = if opts[:limit].nil?
                       @config['scrape_limit']
                     else
                       opts[:limit]
                     end
      submissions = @client.subreddit(subreddit).hot limit: scrape_limit
      return submissions
    end
  end

  # Gets the users commenting in a submission and appends them to an array.
  # @!method get_users(user_list, submission)
  # @param user_list [Array] The list of users to append to.
  # @param submission [NeonRAW::Objects::Submission] The submission object to
  #   scan.
  def get_users(user_list, submission)
    reddit_exception_handling do
      user_list << submission.author
      comments = @client.flatten_tree(submission.comments)
      comments.each do |comment|
        if comment.morecomments?
          subreddit = submission.subreddit
          more_comments = nil
          reddit_exception_handling do
            more_comments = comment.expand(subreddit)
            break
          end
          more_comments.each { |new_comment| user_list << new_comment.author }
        else
          user_list << comment.author
        end
      end
      break
    end
  end

  # Fetches a listing of a user's post history.
  # @!method get_overview(username)
  # @param username [String] The username of the user.
  # @return [NeonRAW::Objects::Listing, nil] Returns either the overview or nil
  #   if the user is shadowbanned.
  def get_overview(username)
    reddit_exception_handling do
      user = @client.user username
      overview_limit = @config['overview_limit']
      overview = user.overview limit: overview_limit
      return overview
    end
  end

  # Goes through an overview listing to get info.
  # @!method gather_user_data(overview)
  # @param overview [NeonRAW::Objects::Listing] The overview of the user.
  # @return [Array] Returns an array containing hashes with the subreddit, id,
  #   and score of various submissions.
  def gather_user_data(overview)
    data = []
    overview.each do |item|
      type = 'comment' if item.comment?
      type = 'submission' if item.submission?
      data << { 'subreddit' => item.subreddit, 'id' => item.id,
                'score' => item.score, 'type' => type }
    end
    data
  end

  # Tallies user data and calls for it to be written to disk.
  # @!method tally_user_data(username, user_data, overlap_tally)
  # @param username [String] The username of the user.
  # @param user_data [Array] Array of hashes containing the user data.
  # @param overlap_tally [Hash] Hash where new values default to 0 to store
  #   the tallies of overlapping users in their corresponding subreddits.
  def tally_user_data(username, user_data, overlap_tally)
    already_done = []
    write_to_users_db(username, user_data)
    user_data.each do |post|
      next if already_done.include?(post['subreddit'])
      already_done << post['subreddit']
      if post['score'] >= @config['min_score']
        overlap_tally[post['subreddit']] += 1
      end
    end
  end

  # Handles exceptions for things that involve getting data from Reddit.
  # @!method reddit_exception_handling
  # @param block [&block] The block to have exceptions handled.
  def reddit_exception_handling
    loop do
      begin
        yield
      # user is shadowbanned or subreddit is banned; couldn't access the
      # user's overview.
      rescue NotFound, PermissionDenied
        return nil
      rescue CouldntReachServer, InternalServerError, ServiceUnavailable
        sleep(5)
        redo
      end
    end
  end

  private :reddit_exception_handling
end
