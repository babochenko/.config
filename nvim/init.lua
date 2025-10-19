vim.g.mapleader = ' '
vim.opt.fixendofline = false

vim.opt.tabstop = 4       -- Number of visual spaces per TAB
vim.opt.shiftwidth = 4    -- Number of spaces to use for autoindent
vim.opt.softtabstop = 4   -- Number of spaces to use for autoindent
vim.opt.expandtab = true  -- Use spaces instead of tabs

vim.defer_fn(function()
  function setup_defaults()
    vim.opt.clipboard = 'unnamedplus'
    vim.opt.number = true
    vim.opt.relativenumber = true
    vim.opt.smoothscroll = true
    vim.opt.timeoutlen = 200
    vim.opt.ignorecase = true
    vim.opt.smartcase = true
  end
  setup_defaults()

  function setup_treesitter_folding()
    vim.o.foldmethod = "expr"
    vim.o.foldexpr = "nvim_treesitter#foldexpr()"
    vim.o.foldlevel = 99     -- start unfolded
    vim.o.foldlevelstart = 99
    vim.o.foldnestmax = 3    -- optional: limit nesting
  end
  setup_treesitter_folding()

  require 'mappings'
  require 'snippets'
end, 0)

require 'plugins'
require 'autocmd'
require 'ui'
require 'ext/mymath'

require('ext/coderunner').setup_autocmds()
require('ext/clipboard').setup_autocmds()

if #vim.api.nvim_list_uis() == 0 then return end

function setup_transparency()
vim.cmd [[
  highlight Normal      ctermbg=none guibg=none
  highlight NormalNC    ctermbg=none guibg=none
  highlight SignColumn  ctermbg=none guibg=none
  highlight VertSplit   ctermbg=none guibg=none
  highlight StatusLine  ctermbg=none guibg=none
  highlight LineNr      ctermbg=none guibg=none
  highlight EndOfBuffer ctermbg=none guibg=none
]]
end
setup_transparency()

