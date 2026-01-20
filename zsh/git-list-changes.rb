#!/usr/bin/env ruby
require 'json'
require 'net/http'
require 'optparse'
require 'pathname'

def main
  cfg = {
    short: false,
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

    opts.on('-s', '--short', 'Short output') { cfg[:short] = true }
    opts.on('-a', '--all', 'Include all commits') { cfg[:all] = true }
    opts.on('-m', '--master', 'Check against origin/master') { cfg[:master] = true }
  end

  parser.parse!
  abort(parser.to_s) if ARGV.empty?

  from, to = parse_range(ARGV[0], cfg[:masger])
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

  puts "\n>>>> #{mod}" unless mod.empty?

  git_log.lines.each do |commit|
    hash, msg = commit.strip.split(' ', 2)
    puts "\n\e[33m#{hash}\e[0m #{msg}" if !short

    if match = msg.match(/pull request #(\d+)/)
      show_pr(match[1], short)
    end
  end
end

def show_pr(pr_num, short)
  user = ENV['X_BITBUCKET_USER']
  pass = ENV['X_BITBUCKET_PW']
  repo = ENV['X_BITBUCKET_REPOSITORY']
  return unless user && pass && repo

  dir = Pathname.pwd.basename.to_s
  uri = URI("https://api.bitbucket.org/2.0/repositories/#{repo}/#{dir}/pullrequests/#{pr_num}?fields=title,author.nickname,updated_on")

  begin
    req = Net::HTTP::Get.new(uri)
    req.basic_auth(user, pass)
    req['Accept'] = 'application/json'

    res = Net::HTTP.start(uri.hostname, uri.port, use_ssl: true, read_timeout: 10) do |http|
      http.request(req)
    end

    return unless res.is_a?(Net::HTTPSuccess)

    data = JSON.parse(res.body)
    title = data['title']
    nickname = data['author']['nickname']
    updated = data['updated_on']
    ticket = title[/[A-Z]+-[0-9]+/]

    pr_url = "https://bitbucket.org/#{repo}/#{dir}/pull-requests/#{pr_num}"

    if short
      puts "@#{nickname} #{title} (#{pr_url})"
    else
      puts "\t@#{nickname} #{pr_url} (#{title})"
      puts "\tTicket: https://#{repo}.atlassian.net/browse/#{ticket}" if ticket
      puts "\tMerged At: #{updated}"
    end
  rescue StandardError
    # Silently fail on network/parse errors
  end
end

main if __FILE__ == $PROGRAM_NAME

