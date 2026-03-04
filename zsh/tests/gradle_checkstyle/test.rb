#!/usr/bin/env ruby
require 'json'
require 'fileutils'
require 'tempfile'

SCRIPT_DIR = File.expand_path(File.dirname(__FILE__))
TEST_FILE = File.join(SCRIPT_DIR, "TestClass.java")
EXPECTED_FILE = File.join(SCRIPT_DIR, "TestClass.java.expected")
BACKUP_FILE = File.join(SCRIPT_DIR, "TestClass.java.backup")

require_relative '../../gradle-checkstyle.rb'

class GradleCheckstyleTest
  def initialize
    @tests_passed = 0
    @tests_failed = 0
  end

  def run_all_tests
    puts "=" * 60
    puts "Running gradle-checkstyle.rb tests"
    puts "=" * 60

    FileUtils.cp(TEST_FILE, BACKUP_FILE)

    begin
      test_error_extraction
      test_ollama_fix
    ensure
      FileUtils.mv(BACKUP_FILE, TEST_FILE) if File.exist?(BACKUP_FILE)
    end

    print_results
  end

  private

  def test_error_extraction
    puts "\n[TEST] Error extraction from gradle output"

    mock_output = <<~OUTPUT
      > Task :checkstyleMain
      [ant:checkstyle] [ERROR] #{TEST_FILE}:5:8: Unused import - java.util.concurrent.Executors. [UnusedImports]

      BUILD FAILED in 2s
    OUTPUT

    errors = extract_checkstyle_errors(mock_output)

    assert_equal(1, errors.size, "Should extract 1 error")
    assert_equal(TEST_FILE, errors[0][:file], "File path should match")
    assert_equal(5, errors[0][:line], "Line number should be 5")
    assert_equal(8, errors[0][:column], "Column should be 8")
    assert_true(errors[0][:message].include?("Unused import"), "Error message should mention unused import")
    assert_equal("UnusedImports", errors[0][:rule], "Rule should be UnusedImports")

    puts "  ✓ Error extraction working correctly"
  end

  def test_ollama_fix
    puts "\n[TEST] Ollama fix and comparison with expected output"

    unless ollama_available?
      puts "  ⚠ Skipping Ollama test - Ollama not available"
      puts "    Install Ollama and pull qwen2.5-coder:7b to run this test"
      return
    end

    error = {
      file: TEST_FILE,
      line: 5,
      column: 8,
      message: "Unused import - java.util.concurrent.Executors.",
      rule: "UnusedImports"
    }

    file_content = File.read(TEST_FILE)
    expected_content = File.read(EXPECTED_FILE).strip

    puts "  → Asking Ollama to fix the error..."
    fixed_content = ask_ollama_to_fix(error, file_content, "qwen2.5-coder:7b")

    if fixed_content.nil? || fixed_content.empty?
      fail_test("Ollama returned empty or nil response")
      return
    end

    File.write(TEST_FILE, fixed_content)
    actual_content = File.read(TEST_FILE).strip

    if normalize(actual_content) == normalize(expected_content)
      @tests_passed += 1
      puts "  ✓ Ollama fix matches expected output"
    else
      fail_test("Ollama fix does not match expected output")
      puts "\n  Expected:\n  " + expected_content.lines.map(&:rstrip).join("\n  ")
      puts "\n  Got:\n  " + actual_content.lines.map(&:rstrip).join("\n  ")
      puts "\n  ✓ But the unused import was removed (partial success)" unless actual_content.include?("java.util.concurrent.Executors")
    end
  end

  def ollama_available?
    response = `curl -s http://localhost:11434/api/version 2>&1`
    !response.empty? && response.include?("version")
  end

  def normalize(content)
    content.gsub(/\r\n/, "\n").strip
  end

  def assert_equal(expected, actual, message)
    if expected == actual
      @tests_passed += 1
    else
      fail_test("#{message}\n  Expected: #{expected.inspect}\n  Got: #{actual.inspect}")
    end
  end

  def assert_true(condition, message)
    if condition
      @tests_passed += 1
    else
      fail_test(message)
    end
  end

  def fail_test(message)
    @tests_failed += 1
    puts "  ✗ FAILED: #{message}"
  end

  def print_results
    puts "\n" + "=" * 60
    puts "Test Results: #{@tests_passed} passed, #{@tests_failed} failed"
    puts "=" * 60

    if @tests_failed == 0
      puts "✓ All tests passed!"
      exit 0
    else
      puts "✗ Some tests failed"
      exit 1
    end
  end
end

if __FILE__ == $0
  GradleCheckstyleTest.new.run_all_tests
end
