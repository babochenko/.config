if #vim.api.nvim_list_uis() == 0 then return end

local function autocmd(name, opts)
  vim.api.nvim_create_autocmd(name, opts)
end

autocmd("FileType", { pattern = "csv", callback = function()
  vim.cmd("CsvViewEnable")
end })

autocmd('FileType', { pattern = 'sql', callback = function()
  vim.bo.commentstring = '-- %s'
end })

-- indent folding scores a line as indent/shiftwidth, so under the global
-- shiftwidth=4 a 2-space function body lands on level 0 and never folds.
-- Shell files here mix 2- and 4-space bodies; shiftwidth=2 makes both fold.
-- Re-asserting foldmethod is what forces the folds to be recomputed.
autocmd('FileType', { pattern = { '*' }, callback = function()
  vim.bo.shiftwidth = 2
  vim.wo.foldmethod = 'indent'
end })



autocmd('TextYankPost', { callback = function()
  vim.highlight.on_yank()
end })

vim.schedule(function()
  local MARKS = require 'ext/marks'
  MARKS.load_marks()
  autocmd('VimLeavePre', { callback = MARKS.save_marks, })
  autocmd('BufReadPost', { callback = MARKS.on_buf_read, })
end)

-- user event that loads after UIEnter + only if file buf is there
autocmd({ 'UIEnter', 'BufReadPost', 'BufNewFile' }, {
  group = vim.api.nvim_create_augroup('NvFilePost', { clear = true }),
  callback = function(args)
    local file = vim.api.nvim_buf_get_name(args.buf)
    local buftype = vim.api.nvim_get_option_value('buftype', { buf = args.buf })

    if not vim.g.ui_entered and args.event == 'UIEnter' then
      vim.g.ui_entered = true
    end

    if file ~= '' and buftype ~= 'nofile' and vim.g.ui_entered then
      vim.api.nvim_exec_autocmds('User', { pattern = 'FilePost', modeline = false })
      vim.api.nvim_del_augroup_by_name 'NvFilePost'

      vim.schedule(function()
        vim.api.nvim_exec_autocmds('FileType', {})

        if vim.g.editorconfig then
          require('editorconfig').config(args.buf)
        end
      end)
    end
  end,
})

-- Add error handling for invalid window operations
autocmd("User", {
  pattern = "LazyVimStarted",
  callback = function()
    -- Suppress treesitter errors for invalid windows
    local original_nvim_redraw = vim.api.nvim__redraw
    vim.api.nvim__redraw = function(opts)
      local ok, err = pcall(original_nvim_redraw, opts)
      if not ok and string.match(err, "Invalid window id") then
        -- Silently ignore invalid window errors
        return
      elseif not ok then
        error(err)
      end
    end
  end,
})

autocmd("BufReadPost", {
  pattern = "*",
  callback = function(args)
    local buf = args.buf
    local line_count = vim.api.nvim_buf_line_count(buf)
    if line_count <= 10000 then return end

    vim.schedule(function()
      if not vim.api.nvim_buf_is_valid(buf) then return end

      vim.bo[buf].syntax = "OFF"
      vim.bo[buf].swapfile = false
      vim.bo[buf].undofile = false

      -- these are window-local, not buffer-local: they have to be set per
      -- window showing the buffer, not via vim.bo/vim.wo indexed by bufnr
      for _, win in ipairs(vim.fn.win_findbuf(buf)) do
        for opt, val in pairs({
          foldmethod = "indent",
          number = false,
          relativenumber = false,
          cursorline = false,
          cursorcolumn = false,
          wrap = false,
          spell = false,
        }) do
          vim.api.nvim_set_option_value(opt, val, { win = win })
        end
      end

      pcall(vim.treesitter.stop, buf)
      vim.diagnostic.enable(false, { bufnr = buf })
    end)
  end,
})

autocmd("BufWinLeave", {
  pattern = "*",
  command = "silent! mkview",
})

autocmd("BufWinEnter", {
  pattern = "*",
  command = "silent! loadview",
})

-- Folds exist from the moment a file opens, and all start open.
-- Runs after the loadview autocmd above so it overrides the ~80 stale view
-- files on disk that still carry "setlocal foldmethod=manual" + "zE" from
-- before 'folds' was dropped from viewoptions.
-- Guarded per buffer so revisiting a window does not reopen folds you closed.
autocmd("BufWinEnter", {
  pattern = "*",
  callback = function(args)
    if vim.wo.foldmethod == "diff" then return end
    if vim.b[args.buf].folds_initialised then return end
    vim.b[args.buf].folds_initialised = true

    vim.wo.foldignore = ""
    vim.wo.foldmethod = "indent"
    vim.wo.foldenable = true
    vim.wo.foldlevel = 99
  end,
})

