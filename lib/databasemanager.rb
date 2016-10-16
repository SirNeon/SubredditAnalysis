require 'pg'

# rubocop:disable Metrics/LineLength

# Handles everything that involves interacting with the postgresql database.
module DatabaseManager
  # Creates database tables.
  # @!method create_tables
  def create_tables
    @db = PG.connect(hostaddr: @config['hostaddr'],
                     port: @config['port'], dbname: @config['data_db'],
                     user: @config['user'])
    @db.exec('CREATE TABLE IF NOT EXISTS users(thing_name text,
                                               subreddit text, id text,
                                               score integer, type text)')

    @db.exec('CREATE TABLE IF NOT EXISTS subreddits(thing_name text,
                                                    overlap text,
                                                    users integer)')

    @db.exec('CREATE TABLE IF NOT EXISTS user_queue(username text)')
  end

  # Fetches data from the database.
  # @!method fetch_users_data(username)
  # @!method fetch_subreddits_data(subreddit)
  # @param thing_name [String] The name of the thing whose data you want.
  # @return [Array] Returns an array of hash tables containing the data.
  %w(users subreddits).each do |type|
    define_method :"fetch_#{type}_data" do |thing_name|
      @db.prepare('select_data', "SELECT * FROM #{type} WHERE thing_name=$1")
      cur = @db.exec_prepared('select_data', [thing_name])

      data = []
      cur.each do |row|
        row['score'] = row['score'].to_i if type == 'users'
        row['users'] = row['users'].to_i if type == 'subreddits'
        data << row
      end
      @db.exec('DEALLOCATE select_data')
      data
    end
  end

  # Writes data to the database.
  # @!method write_to_users_db(username, user_data)
  # @!method write_to_subreddits_db(subreddit, subreddit_data)
  # @param thing_name [String] The name of the thing who data you want written.
  # @param thing_data [Array] An array of hash tables containing the data.
  %w(users subreddits).each do |type|
    define_method :"write_to_#{type}_db" do |thing_name, thing_data|
      check = public_send(:"fetch_#{type}_data", thing_name)
      return nil unless check.empty?

      thing_data.each do |thing|
        data = []
        if type == 'users'
          data += [thing_name, thing['subreddit'], thing['id'],
                   thing['score'], thing['type']]
          @db.prepare('data_insert', "INSERT INTO #{type} VALUES($1, $2, $3, $4, $5)")
        else
          data += [thing_name, thing['overlap'], thing['users']]
          @db.prepare('data_insert', "INSERT INTO #{type} VALUES($1, $2, $3)")
        end
        @db.exec_prepared('data_insert', data)
        @db.exec('DEALLOCATE data_insert')
      end
    end
  end

  # Grabs a user from the queue to get their overview.
  # @!method fetch_user_from_queue
  # @return [String] The username of the user.
  def fetch_user_from_queue
    cur = @db.exec('SELECT * FROM user_queue FETCH FIRST ROW ONLY')
    user = ''
    cur.each { |row| user += row['username'] unless row.empty? }
    @db.prepare('delete_user', 'DELETE FROM user_queue WHERE username=$1')
    @db.exec_prepared('delete_user', [user])
    @db.exec('DEALLOCATE delete_user')
    user
  end

  # Puts users in the queue in the database.
  # @!method write_users_to_queue(user_list)
  # @param user_list [Array] An array of strings containing the users.
  def write_users_to_queue(user_list)
    user_list.each do |user|
      @db.prepare('user_insert', 'INSERT INTO user_queue VALUES($1)')
      @db.exec_prepared('user_insert', [user])
      @db.exec('DEALLOCATE user_insert')
    end
  end

  # Close the database connections
  # @!method clean_up
  def clean_up
    @db.close if @db
  end
end
