local function reset_hunk()
  local relpath = vim.fn.expand('%')
  local git_lines = vim.fn.systemlist('git show HEAD:' .. relpath)
  if vim.v.shell_error ~= 0 or #git_lines == 0 then
    vim.notify("Failed to get file from git", vim.log.levels.ERROR)
    return
  end

  local mode = vim.fn.mode()
  if mode == 'v' or mode == 'V' then
    local start_line = vim.fn.line("'<") - 1
    local end_line = vim.fn.line("'>")
    local replacement = {}
    for i = start_line + 1, end_line do
      table.insert(replacement, git_lines[i] or "")
    end
    vim.api.nvim_buf_set_lines(0, start_line, end_line, false, replacement)
    vim.cmd("normal! gv")  -- reselect visual for confirmation
    vim.notify("Reset selected lines to HEAD")
  else
    local curr = vim.fn.line('.') - 1
    local line = git_lines[curr + 1]
    if line then
      vim.api.nvim_set_current_line(line)
      vim.notify("Reset line " .. (curr + 1) .. " to HEAD")
    else
      vim.notify("Could not retrieve line from git", vim.log.levels.WARN)
    end
  end
end

return {
  reset_hunk = reset_hunk,
}

