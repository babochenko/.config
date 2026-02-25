#!/usr/bin/env ruby
require 'json'
require 'net/http'
require 'optparse'
require 'pathname'

def main
  cfg = {
    short: true,
    all: false,
    master: false,
  }

  parser = OptionParser.new do |opts|
    opts.banner = <<~USAGE
      Usage: git-list-changes [options] <start-commit> [dir]

      Parameters:
          start-commit (required) - a commit or range of commits (..) to display the diff for
          dir          (optional) - if you need diff not for the entire repository, but for a subdirectory

      Examples:
          git-list-changes d5bff459f963
          git-list-changes d5bff459f963..e266dd4e6a55 mymodule

      Options:
    USAGE

    opts.on('-f', '--full', 'Full output') { cfg[:short] = false }
    opts.on('-a', '--all', 'Include all commits') { cfg[:all] = true }
    opts.on('-m', '--master', 'Check against origin/master') { cfg[:master] = true }
  end

  parser.parse!
  abort(parser.to_s) if ARGV.empty?

  from, to = parse_range(ARGV[0], cfg[:master])
  dir = ARGV[1] || ''
  modules = dir.empty? ? find_modules : [dir]

  modules.each { |mod| process_module(mod, from, to, cfg) }
end

def main_branch
  %w[main master].find do |name|
    system("git rev-parse --verify #{name} > /dev/null 2>&1")
  end || abort("No 'main' or 'master' branch found")
end

def parse_range(range, is_master)
  from, to = range.split('..', 2)
  return [from, "origin/master"] if is_master
  return [from, to || "origin/#{main_branch}"]
end

def find_modules
  `find . -maxdepth 2 -name build.gradle`.lines
    .map { |l| Pathname.new(l.strip).dirname.to_s }
    .reject { |d| d == '.' }
end

def process_module(mod, from, to, cfg)
  short = cfg[:short]
  commits = cfg[:all] ? '' : "--grep '^Merged'"

  git_log = `git log origin/#{main_branch} --oneline #{from}..#{to} #{commits} -- #{mod}`.strip
  return if git_log.empty?

  prs = git_log.lines.map do |commit|
    hash, msg = commit.strip.split(' ', 2)
    next unless (match = msg.match(/pull request #(\d+)/))
    fetch_pr(match[1], hash, msg)
  end.compact

  return if prs.empty?

  puts "\n\e[33m>>>> #{mod} (#{prs.size} PRs)\e[0m" unless mod.empty?

  if short
    by_user = prs.group_by { |pr| pr[:nickname] }
    singles, groups = by_user.partition { |_, list| list.size == 1 }

    singles.each do |nickname, list|
      pr = list.first
      puts "- \e[32m@#{nickname}\e[0m #{pr[:title]} \e[36m(#{pr[:url]})\e[0m"
    end

    puts "" unless singles.empty? || groups.empty?

    groups.each do |nickname, list|
      puts "\e[32m@#{nickname}\e[0m"
      list.each { |pr| puts "- #{pr[:title]} \e[36m(#{pr[:url]})\e[0m" }
      puts ""
    end
  else
    repo = ENV['X_BITBUCKET_REPOSITORY']
    prs.each do |pr|
      puts "\n\e[33m#{pr[:hash]}\e[0m #{pr[:msg]}"
      puts "\t\e[32m@#{pr[:nickname]}\e[0m #{pr[:url]} (#{pr[:title]})"
      puts "\tTicket: https://#{repo}.atlassian.net/browse/#{pr[:ticket]}" if pr[:ticket]
      puts "\tMerged At: #{pr[:updated]}"
    end
  end
end

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

main if __FILE__ == $PROGRAM_NAME

