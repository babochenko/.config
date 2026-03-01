-- run.lua: run the current file or unsaved buffer by filetype
-- Supports: python, java, lua, haskell, javascript
-- <leader>r in mappings.lua

local function venv_python()
  local venv = os.getenv("VIRTUAL_ENV")
  if venv then
    return venv .. "/bin/python"
  end
  return "python3"
end

local runners = {
  python     = { cmd = venv_python() .. " %s", ext = "py" },
  java       = { cmd = "java %s",              ext = "java" },
  lua        = { cmd = "lua %s",               ext = "lua" },
  haskell    = { cmd = "runghc %s",            ext = "hs" },
  javascript = { cmd = "node %s",              ext = "js" },
}

local function run_in_terminal(cmd)
  vim.cmd('botright split | terminal')
  vim.cmd('startinsert')
  vim.fn.chansend(vim.b.terminal_job_id, cmd .. '\n')
end

local function run()
  local ft = vim.bo.filetype
  local runner = runners[ft]

  if not runner then
    vim.notify('No runner for filetype: ' .. (ft ~= '' and ft or '(none)'), vim.log.levels.WARN)
    return
  end

  local file_path = vim.fn.expand('%:p')

  if file_path ~= '' and vim.fn.filereadable(file_path) == 1 then
    run_in_terminal(string.format(runner.cmd, vim.fn.shellescape(file_path)))
  else
    -- Unsaved buffer: dump to a temp file, run, then delete
    local tmp = vim.fn.tempname() .. '.' .. runner.ext
    local lines = vim.api.nvim_buf_get_lines(0, 0, -1, false)
    vim.fn.writefile(lines, tmp)
    local cmd = string.format(runner.cmd, vim.fn.shellescape(tmp))
    run_in_terminal(cmd .. '; rm -f ' .. vim.fn.shellescape(tmp))
  end
end

return {
    venv_python = venv_python,
    run = run,
}
