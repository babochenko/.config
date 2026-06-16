#!/usr/bin/env ruby
require 'date'
require 'time'
require_relative 'bitbucket'

def target_date(arg)
  return Date.today - 1 if arg.nil? || arg.empty?
  return Date.today + arg.to_i if arg.match?(/\A-?\d+\z/)

  Date.parse(arg)
rescue ArgumentError
  abort "Invalid date: #{arg} (expected YYYY-MM-DD, 0 for today, or -N for N days ago)"
end

def state_color(state)
  code = { 'OPEN' => 34, 'MERGED' => 32, 'DECLINED' => 31 }[state]
  code ? "\e[#{code}m#{state}\e[0m" : state
end

def main
  date = target_date(ARGV[0])

  prs = fetch_my_prs
  abort 'Failed to fetch PRs (check X_BITBUCKET_USER / X_BITBUCKET_PW / X_BITBUCKET_REPOSITORY / X_BITBUCKET_UUID)' if prs.nil?

  on_date = prs.select { |pr| pr[:created] && Time.parse(pr[:created]).getlocal.to_date == date }

  if on_date.empty?
    puts "No PRs created on #{date}."
    return
  end

  puts "\e[33m>>>> My PRs created on #{date} (#{on_date.size})\e[0m"
  on_date.sort_by { |pr| pr[:created] }.each do |pr|
    puts "- [#{state_color(pr[:state])}] #{pr[:title]} \e[36m(#{pr[:url]})\e[0m"
  end
end

main if __FILE__ == $PROGRAM_NAME
