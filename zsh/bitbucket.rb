require 'json'
require 'net/http'
require 'pathname'

def fetch_pr(pr_num, hash, msg)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  return nil unless user && pass && repo

  dir = Pathname.pwd.basename.to_s
  uri = URI("https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests/#{pr_num}?fields=title,author.nickname,updated_on")

  begin
    req = Net::HTTP::Get.new(uri)
    req.basic_auth(user, pass)
    req['Accept'] = 'application/json'

    res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
      http.request(req)
    end

    return nil unless res.is_a?(Net::HTTPSuccess)

    data = JSON.parse(res.body)
    title = data['title']
    nickname = data['author']['nickname']
    updated = data['updated_on']
    ticket = title[/[A-Z]+-[0-9]+/]
    pr_url = "https://bitbucket.org/#{repo}/#{dir}/pull-requests/#{pr_num}"

    { nickname: nickname, title: title, updated: updated, ticket: ticket, url: pr_url, hash: hash, msg: msg }
  rescue StandardError
    nil
  end
end

def find_open_pr_for_branch(branch)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  return nil unless user && pass && repo

  dir = Pathname.pwd.basename.to_s
  q = URI.encode_www_form_component("source.branch.name=\"#{branch}\"")
  uri = URI("https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests?q=#{q}&state=OPEN&fields=values.id,values.title")

  begin
    req = Net::HTTP::Get.new(uri)
    req.basic_auth(user, pass)
    req['Accept'] = 'application/json'

    res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
      http.request(req)
    end

    return nil unless res.is_a?(Net::HTTPSuccess)

    pr = JSON.parse(res.body)['values'].first
    return nil unless pr

    { id: pr['id'], title: pr['title'] }
  rescue StandardError
    nil
  end
end

def group_pr_comments(comments)
  inline, general = comments.partition { |c| c[:file] }

  by_id = inline.each_with_object({}) { |c, h| h[c[:id]] = c }

  thread_root = lambda do |c|
    c[:parent_id] && by_id[c[:parent_id]] ? thread_root.call(by_id[c[:parent_id]]) : c
  end

  grouped = inline.group_by { |c| c[:file] }.transform_values do |file_comments|
    file_comments
      .group_by { |c| thread_root.call(c)[:id] }
      .values
      .sort_by { |t| thread_root.call(t.first)[:created_at] || '' }
      .map do |thread|
        root = thread_root.call(thread.first)
        {
          line: root[:line],
          thread: thread.sort_by { |c| c[:created_at] || '' }
        }
      end
  end

  grouped[:general] = general unless general.empty?
  grouped
end

def fetch_pr_comments(pr_num)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  return nil unless user && pass && repo

  dir = Pathname.pwd.basename.to_s
  url = "https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests/#{pr_num}/comments?pagelen=100"

  raw = []

  loop do
    uri = URI(url)
    req = Net::HTTP::Get.new(uri)
    req.basic_auth(user, pass)
    req['Accept'] = 'application/json'

    res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
      http.request(req)
    end

    unless res.is_a?(Net::HTTPSuccess)
      warn "Bitbucket API error #{res.code}: #{res.body}"
      return nil
    end

    data = JSON.parse(res.body)
    raw.concat(data['values'])

    break unless data['next']
    url = data['next']
  end

  raw.reject { |c| c['deleted'] }.map do |c|
    comment = {
      id: c['id'],
      parent_id: c.dig('parent', 'id'),
      author: c.dig('user', 'display_name') || 'unknown',
      body: c.dig('content', 'raw') || '',
      created_at: c['created_on'],
    }

    if (inline = c['inline'])
      comment[:file] = inline['path']
      comment[:line] = inline['to'] || inline['from']
    end

    comment
  end.compact
rescue StandardError => e
  warn "fetch_pr_comments failed: #{e.message}"
  nil
end

