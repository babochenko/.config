# gradle-checkstyle.rb Tests

This directory contains tests for the `gradle-checkstyle.rb` script.

## Test Files

- `TestClass.java` - Java file with a checkstyle error (unused import)
- `TestClass.java.expected` - Blueprint file showing the expected fixed version
- `test_gradle_checkstyle.rb` - Test runner script

## Running Tests

```bash
cd tests
./test_gradle_checkstyle.rb
```

Or from the parent directory:

```bash
ruby tests/test_gradle_checkstyle.rb
```

## What the Tests Cover

### 1. Error Extraction Test
- Mocks gradle checkstyle output with an error
- Tests that `extract_checkstyle_errors()` correctly parses:
  - File path
  - Line number
  - Column number
  - Error message
  - Rule name

### 2. Ollama Fix Test
- Takes a Java file with a checkstyle error (unused import)
- Calls Ollama to fix the error
- Compares the fixed version against the expected blueprint
- Verifies the fix matches the expected output

## Prerequisites

For the full test suite to run:
- **Ollama** must be installed and running
- **qwen2.5-coder:7b** model must be available

If Ollama is not available, the error extraction test will still run, but the Ollama fix test will be skipped.

## Test Output

Successful run:
```
============================================================
Running gradle-checkstyle.rb tests
============================================================

[TEST] Error extraction from gradle output
  ✓ Error extraction working correctly

[TEST] Ollama fix and comparison with expected output
  → Asking Ollama to fix the error...
  ✓ Ollama fix matches expected output

============================================================
Test Results
============================================================
Passed: 6
Failed: 0
============================================================
✓ All tests passed!
```

## Adding New Tests

To add a new test:

1. Create test Java file with checkstyle error
2. Create corresponding `.expected` file with the fix
3. Add test method to `GradleCheckstyleTest` class
4. Call the test method in `run_all_tests`
