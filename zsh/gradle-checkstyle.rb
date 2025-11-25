#!/usr/bin/env ruby

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

# Capture stdout + stderr
output = `#{cmd.join(" ")} 2>&1`

error_lines = []

output.each_line do |line|
  error_lines << line if line.include?("[ERROR]")
end

puts "----- Checkstyle Errors (#{error_lines.size}) -----"
error_lines.each { |l| puts l }

