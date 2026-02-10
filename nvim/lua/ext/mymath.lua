local _visual = require('ext/getvisual').getvisual

local function _writeln(line, value)
  -- If lcol=0 and rcol=-1, it means replace entire line
  if line.lcol == 0 and line.rcol == -1 then
    vim.fn.setline(line.line, value)
  else
    local head = vim.fn.getline(line.line):sub(1, line.lcol-1)
    local tail = vim.fn.getline(line.line):sub(line.rcol+1)
    vim.fn.setline(line.line, head .. value .. tail)
  end
end

local function _num_write(func)
  local vis = _visual()
  if vis == nil then return end

  for _, line in ipairs(vis) do
    local number = tonumber(line.text)
    if not number then
      vim.api.nvim_err_writeln("No valid number selected: " .. line.text)
      return
    end

    _writeln(line, func(number))
  end
end

local function make_cmd1(name, func)
  vim.api.nvim_create_user_command(name, function(opts)
    local factor = tonumber(opts.args)
    if factor then
      func(factor)
    else
      print("Invalid number")
    end
  end, { nargs = 1, range = true })
end

local function make_cmd0(name, func)
  vim.api.nvim_create_user_command(name, func, { nargs = 0, range = true })
end

local MyMath = {
  Add = function(factor) _num_write(function(num) return num + factor end) end,
  Sub = function(factor) _num_write(function(num) return num - factor end) end,
  Mul = function(factor) _num_write(function(num) return num * factor end) end,
  Div = function(factor) _num_write(function(num) return num / factor end) end,
  Pow = function(factor) _num_write(function(num) return num ^ factor end) end,
}

for name, func in pairs(MyMath) do
  make_cmd1(name, func)
end

local function _eval(line)
  local expr = line.text
  if expr:gsub("%s", ""):match('^[.,0-9%+%-%*/()%%^]*$') then
    local safe_expr = expr:gsub("%^", "**")
    local result = load("return " .. safe_expr)
    if result then
      local value = result()
      return "Result: " .. tostring(value)
    else
      return "Invalid expression: " .. safe_expr
    end
  else
    return "Invalid expression: " .. expr
  end
end

local eval_impl = function(use_current_line)
  local vis

  if use_current_line then
    -- Normal mode: use current line
    local current_line_num = vim.fn.line('.')
    local current_line_text = vim.fn.getline('.')
    vis = {{
      text = current_line_text,
      line = current_line_num,
      lcol = 1,
      rcol = #current_line_text
    }}
  else
    -- Visual mode: use visual selection
    vis = _visual()
    if vis == nil or #vis == 0 then return end
  end

  for _, line in ipairs(vis) do
    local text = line.text
    local trimmed = text:match("^(.-)%s*$")

    if trimmed:sub(-1) == '=' then
      local expr = trimmed:sub(1, -2)
      local modified_line = {
        text = expr,
        line = line.line,
        lcol = line.lcol,
        rcol = line.rcol
      }
      local safe_expr = expr:gsub("%s", ""):gsub("%^", "**")

      if safe_expr:match('^[.,0-9%+%-%*/()%%^]*$') then
        local result = load("return " .. safe_expr)
        if result then
          local value = result()
          _writeln(line, expr .. "= " .. value)
        else
          print("Invalid expression: " .. expr)
        end
      else
        print("Invalid expression: " .. expr)
      end
    else
      local res = _eval(line)
      print(res)
    end
  end
end

local eval = function()
  eval_impl(false)
end

local eval_current_line = function()
  eval_impl(true)
end

make_cmd0('Eval', eval)

return {
  _eval = _eval,
  eval = eval,
  eval_current_line = eval_current_line,
}

