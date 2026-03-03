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

def fetch_pr_comments(pr_num)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  return nil unless user && pass && repo

  dir = Pathname.pwd.basename.to_s
  url = "https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests/#{pr_num}/comments?pagelen=100"

  comments = []

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

    data['values'].each do |c|
      next if c['deleted']

      comment = {
        author: c.dig('user', 'display_name') || 'unknown',
        body: c.dig('content', 'raw') || '',
      }

      if (inline = c['inline'])
        comment[:file] = inline['path']
        comment[:line] = inline['to'] || inline['from']
      end

      comments << comment
    end

    break unless data['next']
    url = data['next']
  end

  comments
rescue StandardError => e
  warn "fetch_pr_comments failed: #{e.message}"
  nil
end

