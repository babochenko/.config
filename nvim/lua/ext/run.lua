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

local function run_in_terminal(c)
  vim.cmd('botright split | terminal')
  vim.cmd('startinsert')
  vim.fn.chansend(vim.b.terminal_job_id, c .. '\n')
end

local function cmd(fmt)
  return function(filename)
    run_in_terminal(string.format(fmt, vim.fn.shellescape(filename)))
  end
end

local function run_python(filename)
  local output = {}

  vim.fn.jobstart({ venv_python(), filename }, {
    stdout_buffered = true,
    stderr_buffered = true,

    on_stdout = function(_, data)
      if data then vim.list_extend(output, data) end
    end,

    on_stderr = function(_, data)
      if data then vim.list_extend(output, data) end
    end,

    on_exit = function()
      vim.schedule(function()
        vim.cmd("botright split")
        local buf = vim.api.nvim_create_buf(false, true)
        vim.api.nvim_win_set_buf(0, buf)
        vim.api.nvim_buf_set_lines(buf, 0, -1, false, output)
      end)
    end,
  })
end

local runners = {
  python     = { fn = run_python,          ext = "py"   },
  java       = { fn = cmd("java %s"),      ext = "java" },
  lua        = { fn = cmd("lua %s"),       ext = "lua"  },
  haskell    = { fn = cmd("runghc %s"),    ext = "hs"   },
  javascript = { fn = cmd("node %s"),      ext = "js"   },
}

local function run()
  local ft = vim.bo.filetype
  local runner = runners[ft]

  if not runner then
    vim.notify('No runner for filetype: ' .. (ft ~= '' and ft or '(none)'), vim.log.levels.WARN)
    return
  end

  local file_path = vim.fn.expand('%:p')

  local file
  if file_path ~= '' and vim.fn.filereadable(file_path) == 1 then
    file = file_path
  else
    file = vim.fn.tempname() .. '.' .. runner.ext
    vim.fn.writefile(vim.api.nvim_buf_get_lines(0, 0, -1, false), tmp)
  end

  runner.fn(file)
end

return {
  venv_python = venv_python,
  run = run,
}

