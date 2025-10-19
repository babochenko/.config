if #vim.api.nvim_list_uis() == 0 then return end

vim.diagnostic.config({
  virtual_text = false,  -- Disable inline virtual text
  signs = true,          -- Keep gutter signs
  underline = true,      -- Keep underline
  update_in_insert = false, -- Disable updates in insert mode
  severity_sort = true,  -- Sort by severity
  float = { border = "rounded" }, -- Customize floating windows
})

require('telescope').setup {
  defaults = {
    previewer = true, -- Globally enable the previewer
    borderchars = { '─', '│', '─', '│', '╭', '╮', '╯', '╰' }, -- Customize border style
    win_options = {
      winblend = 10, -- Add transparency if desired
    },
    border = true, -- Enable the border
    layout_strategy = 'horizontal',
    layout_config = {
      horizontal = {
        prompt_position = 'top',
        preview_width = 0.5,
        results_width = 0.8,
      },
      vertical = {
        mirror = false,
      },
      width = 0.87,
      height = 0.80,
      preview_cutoff = 120,
    },
    sorting_strategy = 'ascending',
  },
}

require('lualine').setup {
  options = {
    icons_enabled = true,
    theme = 'onedark',
    component_separators = { left = '', right = ''},
    section_separators = { left = '', right = ''},
    disabled_filetypes = {
      statusline = {},
      winbar = {},
    },
    ignore_focus = {},
    always_divide_middle = true,
    always_show_tabline = true,
    globalstatus = false,
    refresh = {
      statusline = 100,
      tabline = 100,
      winbar = 100,
    }
  },
  sections = {
    lualine_a = {'mode'},
    lualine_b = {'branch', 'diff', 'diagnostics'},
    lualine_c = {'filename'},
    lualine_x = {'encoding', 'fileformat', 'filetype'},
    lualine_y = {'progress'},
    lualine_z = {'location'}
  },
  inactive_sectioms = {
    lualine_a = {},
    lualine_b = {},
    lualine_c = {'filename'},
    lualine_x = {'location'},
    lualine_y = {},
    lualine_z = {}
  },
  tabline = {},
  winbar = {},
  inactive_winbar = {},
  extensions = {}
}

local hl_group = function(group, opts)
  vim.api.nvim_set_hl(0, group, opts)
end

local neutral = "#abb2bf"
local border = "#657088"
local keyword = "#61afef"
local constant = "#c678dd"

hl_group("TelescopeBorder", { fg = border, bg = "#1c1f26" })
hl_group("@module", { fg = neutral })
hl_group("@property", { fg = neutral })
hl_group("@variable", { fg = neutral })
hl_group("@variable.member", { fg = neutral })
hl_group("@variable.parameter", { fg = neutral })

hl_group("@keyword", { fg = keyword })
hl_group("@lsp.type.modifier.java", { link = "@keyword" })
hl_group("@keyword.return", { link = "@keyword" })
hl_group("@keyword.operator", { fg = neutral })
hl_group("@constant", { fg = constant })
hl_group("@lsp.mod.static.java", { fg = constant })

hl_group("@punctuation.bracket", { fg = neutral })
hl_group("@punctuation.delimiter", { fg = border })

