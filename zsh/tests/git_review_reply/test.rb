#!/usr/bin/env ruby
require 'stringio'

require_relative '../../git-review-reply'

class GitReviewReplyTest
  def initialize
    @passed = 0
    @failed = 0
  end

  def run_all
    puts "=" * 60
    puts "Running git-review-reply.rb tests"
    puts "=" * 60

    test_no_open_pr
    test_no_comments_on_pr
    test_fetch_comments_failure
    test_with_unanswered_comments
    test_complex_fixes_not_auto_applied
    test_claude_ratings_parsed_correctly

    print_results
  end

  private

  def capture_stdout
    old = $stdout
    $stdout = StringIO.new
    yield
    $stdout.string
  ensure
    $stdout = old
  end

  def make_api(overrides = {})
    Api.new(
      find_open_pr: ->(_b) { { id: 1, title: "Test PR" } },
      fetch_comments: ->(_id) { [] },
      reply_comment: ->(_pr, _comment, _text) { true },
      rate_comments: ->(_u) { [] },
      apply_fixes: ->(_f) { },
      **overrides
    )
  end

  def test_no_open_pr
    puts "\n[TEST] No open PR for branch"

    api = make_api(find_open_pr: ->(_b) { nil })
    output = capture_stdout { run_review_reply("my-branch", api) }

    assert_includes(output, "No open PR found for branch: my-branch", "Should print no PR message")
    puts "  ✓ Handled no open PR"
  end

  def test_no_comments_on_pr
    puts "\n[TEST] No comments on PR"

    api = make_api(fetch_comments: ->(_id) { [] })
    output = capture_stdout { run_review_reply("my-branch", api) }

    assert_includes(output, "No unanswered inline comments", "Should print no comments message")
    puts "  ✓ Handled no comments"
  end

  def test_fetch_comments_failure
    puts "\n[TEST] Fetch comments fails (returns nil)"

    api = make_api(fetch_comments: ->(_id) { nil })
    output = capture_stdout { run_review_reply("my-branch", api) }

    assert_includes(output, "Failed to fetch comments", "Should print failure message")
    puts "  ✓ Handled fetch failure"
  end

  def test_with_unanswered_comments
    puts "\n[TEST] Has unanswered inline comments"

    comments = [
      { id: 10, parent_id: nil, author: "alice", body: "rename this variable", created_at: "2024-01-01T00:00:00Z", file: "foo.rb", line: 5 }
    ]
    ratings = [
      { "file" => "foo.rb", "line" => 5, "comment" => "rename this variable", "complexity" => 1, "reason" => "simple rename", "summary" => "renamed" }
    ]
    replies = []

    api = Api.new(
      find_open_pr: ->(_b) { { id: 42, title: "Test PR" } },
      fetch_comments: ->(_id) { comments },
      reply_comment: ->(pr_id, comment_id, text) { replies << { pr_id: pr_id, comment_id: comment_id, text: text }; true },
      rate_comments: ->(_u) { ratings },
      apply_fixes: ->(_f) { }
    )

    capture_stdout { run_review_reply("my-branch", api) }

    assert_equal(1, replies.size, "Should post 1 reply")
    assert_equal(42, replies.first[:pr_id], "Should reply on PR 42")
    assert_equal(10, replies.first[:comment_id], "Should reply to comment 10")
    assert_equal("renamed", replies.first[:text], "Reply text should be the summary")
    puts "  ✓ Posted reply to unanswered comment"
  end

  def test_complex_fixes_not_auto_applied
    puts "\n[TEST] Complex fixes (complexity > 2) are not auto-applied"

    comments = [
      { id: 20, parent_id: nil, author: "bob", body: "refactor this module", created_at: "2024-01-01T00:00:00Z", file: "bar.rb", line: 10 }
    ]
    ratings = [
      { "file" => "bar.rb", "line" => 10, "comment" => "refactor this module", "complexity" => 4, "reason" => "large refactor", "summary" => "refactored" }
    ]
    replies = []
    applied = []

    api = Api.new(
      find_open_pr: ->(_b) { { id: 1, title: "PR" } },
      fetch_comments: ->(_id) { comments },
      reply_comment: ->(pr_id, comment_id, text) { replies << { pr_id: pr_id, comment_id: comment_id, text: text }; true },
      rate_comments: ->(_u) { ratings },
      apply_fixes: ->(fixes) { applied.concat(fixes) }
    )

    capture_stdout { run_review_reply("my-branch", api) }

    assert_equal(0, replies.size, "Should not post replies for complex fixes")
    assert_equal(0, applied.size, "Should not auto-apply complex fixes")
    puts "  ✓ Complex fixes skipped"
  end

  def test_claude_ratings_parsed_correctly
    puts "\n[TEST] Multiple comments - mixed complexity"

    comments = [
      { id: 1, parent_id: nil, author: "alice", body: "fix typo", created_at: "2024-01-01T00:00:00Z", file: "a.rb", line: 1 },
      { id: 2, parent_id: nil, author: "bob",   body: "big refactor", created_at: "2024-01-01T00:00:00Z", file: "b.rb", line: 2 },
      { id: 3, parent_id: nil, author: "carol", body: "rename var", created_at: "2024-01-01T00:00:00Z", file: "c.rb", line: 3 }
    ]
    ratings = [
      { "file" => "a.rb", "line" => 1, "comment" => "fix typo",     "complexity" => 0, "reason" => "typo", "summary" => "fixed" },
      { "file" => "b.rb", "line" => 2, "comment" => "big refactor", "complexity" => 5, "reason" => "hard", "summary" => "refactored" },
      { "file" => "c.rb", "line" => 3, "comment" => "rename var",   "complexity" => 1, "reason" => "easy rename", "summary" => "renamed" }
    ]
    replies = []

    api = Api.new(
      find_open_pr: ->(_b) { { id: 1, title: "PR" } },
      fetch_comments: ->(_id) { comments },
      reply_comment: ->(_pr_id, comment_id, text) { replies << { comment_id: comment_id, text: text }; true },
      rate_comments: ->(_u) { ratings },
      apply_fixes: ->(_f) { }
    )

    capture_stdout { run_review_reply("my-branch", api) }

    assert_equal(2, replies.size, "Should reply only to complexity <= 2 comments")
    reply_ids = replies.map { |r| r[:comment_id] }.sort
    assert_equal([1, 3], reply_ids, "Should reply to comments 1 and 3")
    assert_equal("fixed",   replies.find { |r| r[:comment_id] == 1 }&.dig(:text), "Comment 1 summary")
    assert_equal("renamed", replies.find { |r| r[:comment_id] == 3 }&.dig(:text), "Comment 3 summary")
    puts "  ✓ Only easy fixes auto-replied"
  end

  def assert_equal(expected, actual, message)
    if expected == actual
      @passed += 1
    else
      fail_test("#{message}\n  Expected: #{expected.inspect}\n  Got: #{actual.inspect}")
    end
  end

  def assert_includes(str, substr, message)
    if str.include?(substr)
      @passed += 1
    else
      fail_test("#{message}\n  String: #{str.inspect}\n  Expected to include: #{substr.inspect}")
    end
  end

  def fail_test(message)
    @failed += 1
    puts "  ✗ FAILED: #{message}"
  end

  def print_results
    puts "\n" + "=" * 60
    puts "Test Results: #{@passed} passed, #{@failed} failed"
    puts "=" * 60

    if @failed == 0
      puts "✓ All tests passed!"
      exit 0
    else
      puts "✗ Some tests failed"
      exit 1
    end
  end
end

if __FILE__ == $0
  GitReviewReplyTest.new.run_all
end
