local mymath = require("ext.mymath")

-- Store original vim functions
local original_getpos = vim.fn.getpos
local original_visualmode = vim.fn.visualmode
local original_getline = vim.fn.getline
local original_setline = vim.fn.setline

-- Helper to store buffer state
local buffer_lines = {}

function trim(str)
	local indent = str:match("\n([ \t]+)")
	if not indent then
		return str
	end
	return str:gsub("\n" .. indent, "\n"):gsub("^\n", ""):gsub("\n$", "")
end

-- Helper to convert string content to lines array
local function content_to_lines(content)
	local lines = {}
	if content then
		content = trim(content)
		for line in content:gmatch("[^\r\n]+") do
			table.insert(lines, line)
		end
	end
	return lines
end

-- Helper to convert lines array to string content
local function lines_to_content(lines)
	return table.concat(lines, "\n")
end

-- Helper function to mock visual selection and buffer content
local function mock_visual_selection(buffer_content, start_line, end_line, start_col, end_col, mode)
	-- Initialize buffer
	buffer_lines = content_to_lines(buffer_content)

	-- Mock getpos to return visual selection marks
	vim.fn.getpos = function(mark)
		if mark == "'<" then
			return {0, start_line, start_col or 1, 0}
		elseif mark == "'>" then
			return {0, end_line, end_col or #buffer_lines[end_line], 0}
		end
		return {0, 0, 0, 0}
	end

	-- Mock visualmode
	vim.fn.visualmode = function()
		return mode or 'V' -- default to line-wise visual mode
	end

	-- Mock getline to return lines from our buffer
	vim.fn.getline = function(lnum)
		return buffer_lines[lnum] or ""
	end

	-- Mock setline to update our buffer
	vim.fn.setline = function(lnum, text)
		buffer_lines[lnum] = text
	end
end

-- Helper function to restore vim functions
local function restore_vim()
	vim.fn.getpos = original_getpos
	vim.fn.visualmode = original_visualmode
	vim.fn.getline = original_getline
	vim.fn.setline = original_setline
end

-- Test helper: setup buffer, run eval on selection, return result
local function test_eval(initial_content, start_line, end_line, expected_content)
	mock_visual_selection(initial_content, start_line, end_line)
	mymath.eval()
	local result = lines_to_content(buffer_lines)
	restore_vim()
	return result
end

describe("Eval command", function()
	describe("single line evaluation with equals sign", function()
		it("evaluates simple addition", function()
			local result = test_eval([[
				3 + 4 = 
            ]], 1, 1)
			assert.equals([[
				3 + 4 = 7
            ]], result)
		end)

		it("evaluates simple subtraction", function()
			local result = test_eval([[
				10 - 3 = 
            ]], 1, 1)
			assert.equals([[
				10 - 3 = 7
            ]], result)
		end)

		it("evaluates multiplication", function()
			local result = test_eval([[
				5 * 6 = 
            ]], 1, 1)
			assert.equals([[
				5 * 6 = 30
            ]], result)
		end)

		it("evaluates division", function()
			local result = test_eval([[
				20 / 4 = 
            ]], 1, 1)
			assert.equals([[
				20 / 4 = 5
            ]], result)
		end)

		it("evaluates floating point operations", function()
			local result = test_eval([[
				1.5 + 2.5 = 
            ]], 1, 1)
			assert.equals([[
				1.5 + 2.5 = 4.0
            ]], result)
		end)

		it("evaluates complex expressions", function()
			local result = test_eval([[
				(3 + 4) * 2 = 
            ]], 1, 1)
			assert.equals([[
				(3 + 4) * 2 = 14
            ]], result)
		end)

		it("evaluates expressions with parentheses", function()
			local result = test_eval([[
				((10 + 5) / 3) - 2 = 
            ]], 1, 1)
			assert.equals([[
				((10 + 5) / 3) - 2 = 3.0
            ]], result)
		end)

		it("evaluates power operation", function()
			local result = test_eval([[
				2 ^ 3 = 
            ]], 1, 1)
			assert.equals([[
				2 ^ 3 = 8.0
            ]], result)
		end)

		it("evaluates modulo operation", function()
			local result = test_eval([[
				10 % 3 = 
            ]], 1, 1)
			assert.equals([[
				10 % 3 = 1
            ]], result)
		end)

		it("handles expression with trailing spaces", function()
			local result = test_eval([[
				7 + 8 =   
            ]], 1, 1)
			assert.equals([[
				7 + 8 = 15
            ]], result)
		end)

		it("handles expression without spaces", function()
			local result = test_eval([[
				12+8=
            ]], 1, 1)
			assert.equals([[
				12+8= 20
            ]], result)
		end)
	end)

	describe("single line in multi-line file", function()
		it("updates only selected line", function()
			local result = test_eval([[
				first line unchanged
				3 + 4 =
				third line unchanged
            ]], 2, 2)
			assert.equals([[
				first line unchanged
				3 + 4 = 7
				third line unchanged
            ]], result)
		end)

		it("updates first line only", function()
			local result = test_eval([[
				5 * 2 =
				second line
				third line
            ]], 1, 1)
			assert.equals([[
				5 * 2 = 10
				second line
				third line
            ]], result)
		end)

		it("updates last line only", function()
			local result = test_eval([[
				first line
				second line
				8 - 3 =
            ]], 3, 3)
			assert.equals([[
				first line
				second line
				8 - 3 = 5
            ]], result)
		end)
	end)

	describe("multiline visual selection", function()
		it("evaluates multiple lines with equals sign", function()
			local result = test_eval([[
				3 + 4 =
				10 - 2 =
				5 * 3 =
            ]], 1, 3)
			assert.equals([[
				3 + 4 = 7
				10 - 2 = 8
				5 * 3 = 15
            ]], result)
		end)

		it("evaluates mixed simple and complex expressions", function()
			local result = test_eval([[
				1 + 1 =
				(5 + 3) * 2 =
				100 / 10 =
            ]], 1, 3)
			assert.equals([[
				1 + 1 = 2
				(5 + 3) * 2 = 16
				100 / 10 = 10
            ]], result)
		end)

		it("evaluates multiple floating point operations", function()
			local result = test_eval([[
				1.5 + 2.5 =
				3.3 * 2 =
				10.5 / 3 =
            ]], 1, 3)
			assert.equals([[
				1.5 + 2.5 = 4.0
				3.3 * 2 = 6.6
				10.5 / 3 = 3.5
            ]], result)
		end)

		it("evaluates expressions with different operators", function()
			local result = test_eval([[
				2 ^ 4 =
				15 % 4 =
				(10 - 3) + 2 =
            ]], 1, 3)
			assert.equals([[
				2 ^ 4 = 16.0
				15 % 4 = 3
				(10 - 3) + 2 = 9
            ]], result)
		end)

		it("handles multiline with varying whitespace", function()
			local result = test_eval([[
				1+2=
				3 + 4 =
				5  +  6  =
            ]], 1, 3)
			assert.equals([[
				1+2= 3
				3 + 4 = 7
				5  +  6  = 11
            ]], result)
		end)

		it("evaluates partial selection in larger file", function()
			local result = test_eval([[
				untouched line 1
				2 + 2 =
				3 * 3 =
				untouched line 2
            ]], 2, 3)
			assert.equals([[
				untouched line 1
				2 + 2 = 4
				3 * 3 = 9
				untouched line 2
            ]], result)
		end)
	end)

	describe("edge cases", function()
		it("evaluates zero result", function()
			local result = test_eval([[
				5 - 5 = 
            ]], 1, 1)
			assert.equals([[
				5 - 5 = 0
            ]], result)
		end)

		it("evaluates negative result", function()
			local result = test_eval([[
				3 - 10 = 
            ]], 1, 1)
			assert.equals([[
				3 - 10 = -7
            ]], result)
		end)

		it("evaluates with decimal places", function()
			local result = test_eval([[
				10 / 3 = 
            ]], 1, 1)
			assert.is_true(result:match("^10 / 3 = 3%.333"))
		end)

		it("evaluates nested parentheses", function()
			local result = test_eval([[
				((2 + 3) * (4 - 1)) = 
            ]], 1, 1)
			assert.equals([[
				((2 + 3) * (4 - 1)) = 15
            ]], result)
		end)
	end)
end)

