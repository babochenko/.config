#!/usr/bin/env ruby
require 'pathname'
require 'uri'
require_relative 'bitbucket'

def main
  branch = `git symbolic-ref --short HEAD 2>/dev/null`.strip
  abort if branch.empty?

  repo = ENV['X_BITBUCKET_REPOSITORY']
  abort unless repo

  dir = Pathname.pwd.basename.to_s

  if (pr = find_open_pr_for_branch(branch))
    puts "PR: \e[34mhttps://bitbucket.org/#{repo}/#{dir}/pull-requests/#{pr[:id]}\e[0m"
    return
  end

  dest = URI.encode_www_form_component("#{repo}/#{dir}::master")
  source = URI.encode_www_form_component(branch)
  puts "Create PR: \e[34mhttps://bitbucket.org/#{repo}/#{dir}/pull-requests/new?source=#{source}&dest=#{dest}&event_source=branch_detail\e[0m"
end

main if __FILE__ == $PROGRAM_NAME

