local function _format_ts(ms)
  local secs = math.floor(ms / 1000)
  local rem_ms = ms - secs * 1000
  local local_str = os.date("%Y-%m-%d %H:%M:%S", secs)
  local utc_str = os.date("!%Y-%m-%d %H:%M:%S", secs)
  return string.format("%s.%03d local | %s.%03d UTC", local_str, rem_ms, utc_str, rem_ms)
end

local function _parse_and_print(text)
  local digits = text:match("(%d+)")
  if not digits then
    vim.api.nvim_err_writeln("No number found in: " .. text)
    return
  end
  local num = tonumber(digits)
  if not num then
    vim.api.nvim_err_writeln("Invalid number: " .. digits)
    return
  end
  print(digits .. " -> " .. _format_ts(num))
end

local function _number_under_cursor()
  local line = vim.fn.getline('.')
  local col = vim.fn.col('.')

  local start_idx, end_idx = 1, 0
  while true do
    local s, e = line:find("%d+", end_idx + 1)
    if not s then break end
    if col >= s and col <= e then
      return line:sub(s, e)
    end
    if s > col then break end
    start_idx, end_idx = s, e
  end

  local word = vim.fn.expand("<cword>")
  if word:match("^%d+$") then return word end
  return nil
end

local parse_date_cursor = function()
  local num = _number_under_cursor()
  if not num then
    vim.api.nvim_err_writeln("No number under cursor")
    return
  end
  _parse_and_print(num)
end

local parse_date_visual = function()
  local saved = vim.fn.getreg('z')
  local saved_type = vim.fn.getregtype('z')
  vim.cmd('silent normal! gv"zy')
  local text = vim.fn.getreg('z')
  vim.fn.setreg('z', saved, saved_type)

  if not text or text == "" then
    vim.api.nvim_err_writeln("No visual selection")
    return
  end

  for line in (text .. "\n"):gmatch("([^\n]*)\n") do
    if line ~= "" then
      _parse_and_print(line)
    end
  end
end

vim.api.nvim_create_user_command('ParseDate', parse_date_cursor, { nargs = 0, range = true })

return {
  parse_date_cursor = parse_date_cursor,
  parse_date_visual = parse_date_visual,
}
