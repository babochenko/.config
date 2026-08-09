require 'json'
require 'net/http'
require 'pathname'

def warn_bitbucket_error(context)
  return if @bitbucket_error

  @bitbucket_error = context
  warn "\e[31m#{context}\e[0m"
end

def bitbucket_error_message(res)
  detail = begin
    JSON.parse(res.body).dig('error', 'message')
  rescue StandardError
    nil
  end
  detail || (res.body && !res.body.empty? ? res.body.strip[0, 300] : res.message)
end

def fetch_pr(pr_num, hash, msg)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  unless user && pass && repo
    missing = { 'X_BITBUCKET_USER' => user, 'X_BITBUCKET_PW' => pass, 'X_BITBUCKET_REPOSITORY' => repo }
             .reject { |_, v| v && !v.empty? }.keys
    warn_bitbucket_error("bitbucket: missing env #{missing.join(', ')}")
    return nil
  end

  dir = Pathname.pwd.basename.to_s
  uri = URI("https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests/#{pr_num}?fields=title,author.nickname,updated_on")

  begin
    req = Net::HTTP::Get.new(uri)
    req.basic_auth(user, pass)
    req['Accept'] = 'application/json'

    res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
      http.request(req)
    end

    unless res.is_a?(Net::HTTPSuccess)
      warn_bitbucket_error("bitbucket API #{res.code}: #{bitbucket_error_message(res)}")
      return nil
    end

    data = JSON.parse(res.body)
    title = data['title']
    nickname = data['author']['nickname']
    updated = data['updated_on']
    ticket = title[/[A-Z]+-[0-9]+/]
    pr_url = "https://bitbucket.org/#{repo}/#{dir}/pull-requests/#{pr_num}"

    { nickname: nickname, title: title, updated: updated, ticket: ticket, url: pr_url, hash: hash, msg: msg }
  rescue StandardError => e
    warn_bitbucket_error("bitbucket API error: #{e.message}")
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
