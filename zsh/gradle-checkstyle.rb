#!/usr/bin/env ruby
require 'json'

# Check if Ollama is installed, install if missing
def ensure_ollama_installed
  if `which ollama`.strip.empty?
    puts "Ollama not found. Installing..."

    case RUBY_PLATFORM
    when /darwin/
      # macOS - use homebrew
      if `which brew`.strip.empty?
        puts "Error: Homebrew not found. Please install Homebrew first:"
        puts "  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
      end

      puts "Installing Ollama via Homebrew..."
      system("brew install ollama")
    when /linux/
      puts "Installing Ollama for Linux..."
      system("curl -fsSL https://ollama.com/install.sh | sh")
    else
      puts "Error: Unsupported platform. Please install Ollama manually from https://ollama.com"
      exit 1
    end

    # Start Ollama service
    puts "Starting Ollama service..."
    spawn("ollama serve > /dev/null 2>&1")
    sleep 3  # Give it time to start

    puts "✓ Ollama installed and started"
  else
    # Check if Ollama is running
    response = `curl -s http://localhost:11434/api/version`
    if response.empty?
      puts "Starting Ollama service..."
      spawn("ollama serve > /dev/null 2>&1")
      sleep 3
    end
  end
end

# Check if model exists, pull if missing
def ensure_model_available(model_name)
  puts "Checking for model #{model_name}..."

  list_output = `ollama list 2>&1`

  unless list_output.include?(model_name)
    puts "Model #{model_name} not found. Pulling..."
    puts "This may take a few minutes..."

    system("ollama pull #{model_name}")

    if $?.success?
      puts "✓ Model #{model_name} downloaded successfully"
    else
      puts "✗ Failed to pull model #{model_name}"
      exit 1
    end
  else
    puts "✓ Model #{model_name} is available"
  end
end

# Base function to extract checkstyle errors from gradle output
def extract_checkstyle_errors(output)
  errors = []

  output.each_line do |line|
    next unless line.include?("[ERROR]")

    # Parse error line format:
    # [ant:checkstyle] [ERROR] /path/to/file.java:line:col: Error message [RuleName]
    if line =~ /\[ERROR\]\s+(.+?\.java):(\d+):(\d+):\s+(.+?)\s+\[(.+?)\]/
      errors << {
        file: $1,
        line: $2.to_i,
        column: $3.to_i,
        message: $4.strip,
        rule: $5
      }
    end
  end

  errors
end

# Get file content with context around the error line
def get_file_context(file_path, line_num, context_lines = 10)
  return nil unless File.exist?(file_path)

  lines = File.readlines(file_path)
  start_line = [0, line_num - context_lines - 1].max
  end_line = [lines.length - 1, line_num + context_lines - 1].min

  {
    full_content: File.read(file_path),
    context: lines[start_line..end_line].join,
    start_line: start_line + 1,
    end_line: end_line + 1
  }
end

# Ask Ollama to fix the checkstyle issue
def ask_ollama_to_fix(error, file_content, model)
  prompt = <<~PROMPT
    Fix this checkstyle error in the Java file.

    Error: #{error[:message]} [#{error[:rule]}]
    Location: Line #{error[:line]}, Column #{error[:column]}

    File content:
    ```java
    #{file_content}
    ```

    Return ONLY the complete fixed file content, no explanations or markdown.
  PROMPT

  request = {
    model: model,
    prompt: prompt,
    stream: false,
    options: {
      temperature: 0.1
    }
  }.to_json

  response = `curl -s -X POST http://localhost:11434/api/generate -d '#{request.gsub("'", "'\\''")}' -H 'Content-Type: application/json'`

  begin
    result = JSON.parse(response)
    fixed_content = result['response']

    # Strip markdown code blocks if present
    fixed_content.gsub!(/```java\n/, '')
    fixed_content.gsub!(/```\n?$/, '')
    fixed_content.strip
  rescue JSON::ParserError => e
    puts "Error parsing Ollama response: #{e.message}"
    nil
  end
end

# Apply the fix to the file
def apply_fix(file_path, fixed_content)
  File.write(file_path, fixed_content)
  puts "✓ Applied fix to #{file_path}"
end

# Main execution
if __FILE__ == $0
  MODEL_NAME = "qwen2.5-coder:7b"

  # Ensure Ollama and model are ready
  ensure_ollama_installed
  ensure_model_available(MODEL_NAME)

  cmd = [
    "./gradlew", "check",
    "-x", "generateAlphaSchema",
    "-x", "compileJava",
    "-x", "compileTestJava",
    "-x", "compileTestDataJava",
    "-x", "compileTestFunctionalJava",
    "-x", "test",
    "-x", "testFunctional"
  ]

  puts "\nRunning gradle checkstyle..."
  output = `#{cmd.join(" ")} 2>&1`

  errors = extract_checkstyle_errors(output)

  puts "\n----- Checkstyle Errors (#{errors.size}) -----"
  errors.each do |err|
    puts "[#{err[:rule]}] #{err[:file]}:#{err[:line]}:#{err[:column]}"
    puts "  #{err[:message]}"
  end

  if errors.empty?
    puts "\n✓ No checkstyle errors found!"
    exit 0
  end

  puts "\n----- Fixing errors with Ollama -----"

  errors.group_by { |e| e[:file] }.each do |file, file_errors|
    puts "\nProcessing #{file} (#{file_errors.size} error(s))..."

    unless File.exist?(file)
      puts "  ✗ File not found: #{file}"
      next
    end

    file_content = File.read(file)

    file_errors.each do |error|
      puts "  Fixing: #{error[:message]}"

      fixed_content = ask_ollama_to_fix(error, file_content, MODEL_NAME)

      if fixed_content && !fixed_content.empty?
        apply_fix(file, fixed_content)
        file_content = fixed_content  # Use fixed content for next error
      else
        puts "  ✗ Failed to get fix from Ollama"
      end
    end
  end

  puts "\n✓ Done!"
end

