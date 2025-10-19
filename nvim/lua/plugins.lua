local home = vim.fn.expand("$HOME")

local plugins_cfg = {
  defaults = { lazy = true },
  install = { colorscheme = { 'onedark' } },

  ui = {
    icons = {
      ft = '',
      lazy = '󰂠 ',
      loaded = '',
      not_loaded = '',
    },
  },

  performance = {
    rtp = {
      disabled_plugins = {
        '2html_plugin',
        'tohtml',
        'getscript',
        'getscriptPlugin',
        'gzip',
        'logipat',
        'netrw',
        'netrwPlugin',
        'netrwSettings',
        'netrwFileHandlers',
        'matchit',
        'tar',
        'tarPlugin',
        'rrhelper',
        'spellfile_plugin',
        'vimball',
        'vimballPlugin',
        'zip',
        'zipPlugin',
        'tutor',
        'rplugin',
        'syntax',
        'synmenu',
        'optwin',
        'compiler',
        'bugreport',
        'ftplugin',
      },
    },
  },
}

function EnsureLazy()
  local lazypath = vim.fn.stdpath 'data' .. '/lazy/lazy.nvim'

  if not vim.loop.fs_stat(lazypath) then
    local repo = 'https://github.com/folke/lazy.nvim.git'
    vim.fn.system { 'git', 'clone', '--filter=blob:none', repo, '--branch=stable', lazypath }
  end

  vim.opt.rtp:prepend(lazypath)

  return require 'lazy'
end

EnsureLazy().setup({
  { 'mfussenegger/nvim-jdtls' },

  { 'tpope/vim-fugitive', lazy = false, },

  { 'sindrets/diffview.nvim',
    dependencies = { 'nvim-lua/plenary.nvim' },
    lazy = false,
    config = true,
    opts = {
      view = {
        default = {
          layout = "diff2_horizontal", -- horizontal diffs
        },
      },
      file_panel = {
        listing_style = "list",     -- or "tree"
        win_config = {
          position = "bottom",      -- bottom of the screen
          height = 10,              -- fixed height in lines
          win_opts = {}
        },
      },
    },
  },

  {
    "rbong/vim-flog",
    lazy = true,
    cmd = { "Flog", "Flogsplit", "Floggit" },
    dependencies = {
      "tpope/vim-fugitive",
    },
  },

  { 'nvim-telescope/telescope.nvim' },

  { 'nvim-tree/nvim-tree.lua',
    dependencies = { 'nvim-tree/nvim-web-devicons' },
    config = function()
      require('nvim-tree').setup({
        view = { width = 30 },
        filters = {
            dotfiles = false,
            git_ignored = false,
        },
        git = {
          enable = true,
          ignore = false,
        },
        disable_netrw = true,
        hijack_netrw = true,
        live_filter = {
          prefix = "[FILTER]: ",
          always_show_folders = false,
        },
        actions = {
          open_file = {
            quit_on_open = false,
          },
        },
      })
    end,
  },

  { 'akinsho/bufferline.nvim',
    version = "*",
    dependencies = 'nvim-tree/nvim-web-devicons',
    config = function()
      require('bufferline').setup({
        options = {
          diagnostics = "nvim_lsp",
          separator_style = "none",
          indicator = {
            style = "none",
          },
          show_buffer_close_icons = true,
          show_close_icon = true,
          show_tab_indicators = false,
          enforce_regular_tabs = true,
          always_show_bufferline = true,
        },
        highlights = {
          separator = {
            fg = {attribute = "bg", highlight = "TabLine"},
            bg = {attribute = "bg", highlight = "TabLine"},
          },
          separator_selected = {
            fg = {attribute = "bg", highlight = "Normal"},
            bg = {attribute = "bg", highlight = "Normal"},
          },
          separator_visible = {
            fg = {attribute = "bg", highlight = "TabLine"},
            bg = {attribute = "bg", highlight = "TabLine"},
          },
        },
      })
    end,
  },

  { 'hrsh7th/nvim-cmp',
    dependencies = {
      'hrsh7th/cmp-nvim-lsp',
      'hrsh7th/cmp-buffer',
      'hrsh7th/cmp-path',
      'hrsh7th/cmp-nvim-lua',
      'L3MON4D3/LuaSnip',
      'saadparwaiz1/cmp_luasnip',
      'rafamadriz/friendly-snippets',
    },
    config = function()
      local cmp = require('cmp')
      local luasnip = require('luasnip')
      require('luasnip.loaders.from_vscode').lazy_load()

      cmp.setup({
        snippet = {
          expand = function(args)
            luasnip.lsp_expand(args.body)
          end,
        },
        mapping = cmp.mapping.preset.insert({
          ['<C-d>'] = cmp.mapping.scroll_docs(-4),
          ['<C-f>'] = cmp.mapping.scroll_docs(4),
          ['<C-Space>'] = cmp.mapping.complete(),
          ['<CR>'] = cmp.mapping.confirm({ select = true }),
          ['<Tab>'] = cmp.mapping(function(fallback)
            if cmp.visible() then
              cmp.select_next_item()
            elseif luasnip.expand_or_jumpable() then
              luasnip.expand_or_jump()
            else
              fallback()
            end
          end, { 'i', 's' }),
        }),
        sources = cmp.config.sources({
          { name = 'nvim_lsp' },
          { name = 'luasnip' },
          { name = 'nvim_lua' },
        }, {
          { name = 'buffer' },
          { name = 'path' },
        }),
      })
    end,
  },

  { 'neovim/nvim-lspconfig',
    dependencies = { 'hrsh7th/cmp-nvim-lsp' },
    event = { "BufReadPre", "BufNewFile" },
    config = function()
      local capabilities = require('cmp_nvim_lsp').default_capabilities()
      local lspconfig = require('lspconfig')

      -- Add on_attach function for keybindings
      local on_attach = function(client, bufnr)
        local opts = { noremap=true, silent=true, buffer=bufnr }
        vim.keymap.set('n', 'gd', vim.lsp.buf.definition, opts)
        vim.keymap.set('n', 'K', vim.lsp.buf.hover, opts)
        vim.keymap.set('n', 'gi', vim.lsp.buf.implementation, opts)
        vim.keymap.set('n', '<C-k>', vim.lsp.buf.signature_help, opts)
        vim.keymap.set('n', '<leader>rn', vim.lsp.buf.rename, opts)
        vim.keymap.set('n', '<leader>ca', vim.lsp.buf.code_action, opts)
        vim.keymap.set('n', 'gr', vim.lsp.buf.references, opts)
        vim.keymap.set('n', '<leader>d', vim.diagnostic.open_float, opts)
        vim.keymap.set('n', '[d', vim.diagnostic.goto_prev, opts)
        vim.keymap.set('n', ']d', vim.diagnostic.goto_next, opts)
      end

      lspconfig.pyright.setup({
        settings = {
          python = {
            pythonPath = home .. "/Developer/.venv/bin/python",
            venvPath = home .. "/Developer",
            venv = ".venv",
            analysis = {
              autoSearchPaths = true,
              useLibraryCodeForTypes = true,
              diagnosticMode = "workspace",
              typeCheckingMode = "basic",
            },
          },
        },
      })

      lspconfig.lua_ls.setup({
        on_attach = on_attach,
        settings = {
          Lua = {
            diagnostics = {
              globals = { "vim" },
            },
          },
        },
      })

      lspconfig.ts_ls.setup({ 
        capabilities = capabilities,
        on_attach = on_attach,
      })

      lspconfig.clangd.setup({ 
        capabilities = capabilities,
        on_attach = on_attach,
      })

      lspconfig.sourcekit.setup({
        cmd = { 'xcrun', 'sourcekit-lsp' },
        root_dir = require('lspconfig.util').root_pattern('*.xcodeproj', '*.xcworkspace', '.git'),
        capabilities = capabilities,
        on_attach = on_attach,
      })

      lspconfig.rust_analyzer.setup({
        settings = {
          ["rust-analyzer"] = {
            cargo = { allFeatures = true },
            check = {
              command = "clippy",
            }
          },
        },
      })
    end,
  },

  { "simrat39/rust-tools.nvim",
    dependencies = { "neovim/nvim-lspconfig" },
    config = function()
      require("rust-tools").setup({})
    end,
  },

  { 'lewis6991/gitsigns.nvim',
    config = function()
      require('gitsigns').setup()
    end,
  },

  { 'folke/which-key.nvim',
    event = "VeryLazy",
    config = function()
      require('which-key').setup()
    end,
  },

  { 'lukas-reineke/indent-blankline.nvim',
    main = "ibl",
    config = function()
      require('ibl').setup({
        indent = { char = "│" },
        scope = { enabled = false },
      })
    end,
  },

  { 'akinsho/toggleterm.nvim',
    version = "*",
    config = function()
      require('toggleterm').setup({
        size = 20,
        open_mapping = [[<c-\>]],
        direction = 'float',
        float_opts = {
          border = 'curved',
        },
      })
    end,
  },

  { 'navarasu/onedark.nvim',
    priority = 1000,
    config = function()
      require('onedark').setup({
        style = 'dark'
      })
      require('onedark').load()
    end,
  },

  { 'kristijanhusak/vim-dadbod-ui',
    dependencies = {
      { 'tpope/vim-dadbod', lazy = true },
      { 'kristijanhusak/vim-dadbod-completion', ft = { 'sql', 'mysql', 'plsql' }, lazy = true },
    },
    cmd = {
      'DBUI',
      'DBUIToggle',
      'DBUIAddConnection',
      'DBUIFindBuffer',
    },
    init = function()
      vim.g.db_ui_use_nerd_fonts = 1
    end,
  },

  { 'stevearc/conform.nvim',
    -- event = 'BufWritePre', -- uncomment for format on save
    config = function()
      require('conform').setup {
        formatters_by_ft = {
          lua = { 'stylua' },
          -- css = { 'prettier' },
          -- html = { 'prettier' },
        },

        -- format_on_save = {
        --   -- These options will be passed to conform.format()
        --   timeout_ms = 500,
        --   lsp_fallback = true,
        -- },
      }
    end,
  },

  { 'nvim-treesitter/nvim-treesitter',
  	opts = {
  		ensure_installed = {
            'css',
            'html',
            'http',
            'lua',
            'markdown',
            'markdown_inline',
            'vim',
            'vimdoc',
        },
        auto_install = true,
        highlight = { enable = true },
  	},
  },

  { "nvim-lualine/lualine.nvim",
    dependencies = { 'nvim-tree/nvim-web-devicons' }
  },

  -- used for tests only now
  { "nvim-lua/plenary.nvim", lazy = true },

  {
      "hat0uma/csvview.nvim",
      ---@module "csvview"
      ---@type CsvView.Options
      opts = {
        parser = { comments = { "#", "//" } },
        keymaps = {
          -- Text objects for selecting fields
          textobject_field_inner = { "if", mode = { "o", "x" } },
          textobject_field_outer = { "af", mode = { "o", "x" } },
          -- Excel-like navigation:
          -- Use <Tab> and <S-Tab> to move horizontally between fields.
          -- Use <Enter> and <S-Enter> to move vertically between rows and place the cursor at the end of the field.
          -- Note: In terminals, you may need to enable CSI-u mode to use <S-Tab> and <S-Enter>.
          jump_next_field_end = { "<Tab>", mode = { "n", "v" } },
          jump_prev_field_end = { "<S-Tab>", mode = { "n", "v" } },
          jump_next_row = { "<Enter>", mode = { "n", "v" } },
          jump_prev_row = { "<S-Enter>", mode = { "n", "v" } },
        },
      },
      cmd = { "CsvViewEnable", "CsvViewDisable", "CsvViewToggle" },
    },

    { "rest-nvim/rest.nvim",
      ft = 'http',
      dependencies = {
        "nvim-treesitter/nvim-treesitter",
        opts = function (_, opts)
          opts.ensure_installed = opts.ensure_installed or {}
          table.insert(opts.ensure_installed, "http")
        end,
      },
      config = function()
        require("rest-nvim").setup({
            env_file = function()
                -- use .env in the same dir as the current buffer (.http file)
                local http_file = vim.api.nvim_buf_get_name(0)
                local dir = vim.fn.fnamemodify(http_file, ":h")
                local env_path = dir .. "/.env"
                if vim.fn.filereadable(env_path) == 1 then
                  return env_path
                end
                return nil -- fallback, no .env found
            end,
            ui = {
                keybinds = {
                    prev = "<S-Tab>",
                    next = "<Tab>",
                },
            },
        })
      end,
    },

  -- 	'williamboman/mason.nvim',
  -- 	opts = {
  -- 		ensure_installed = {
  -- 			'lua-language-server', 'stylua',
  -- 			'html-lsp', 'css-lsp' , 'prettier'
  -- 		},
  -- 	},
  -- },
  --
}, plugins_cfg)

