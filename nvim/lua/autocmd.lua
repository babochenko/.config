if #vim.api.nvim_list_uis() == 0 then return end

local TREE = require('nvim-tree.api')

local function autocmd(name, opts)
  vim.api.nvim_create_autocmd(name, opts)
end

autocmd("FileType", { pattern = "csv", callback = function()
  vim.cmd("CsvViewEnable")
end })

autocmd('FileType', { pattern = 'sql', callback = function()
  vim.bo.commentstring = '-- %s'
end })

autocmd('FileType', { pattern = { 'yml', 'yaml' }, command = 'syntax off' })

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
vim.api.nvim_create_autocmd("User", {
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

