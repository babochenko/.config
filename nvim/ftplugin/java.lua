local home = os.getenv('HOME')
local jdtls = require('jdtls')

local root_dir = require('jdtls.setup').find_root {'gradlew', 'mvnw', '.git'}
local workspace_folder = home .. "/.local/share/eclipse/" .. vim.fn.fnamemodify(root_dir, ":p:h:t")

function map(rhs, lhs, opt, desc)
  opt.desc = desc
  vim.keymap.set("n", rhs, lhs, opt)
end

local on_attach = function(client, bufnr)
  -- Regular Neovim LSP client keymappings
  local opt = { noremap=true, silent=true, buffer=bufnr }
  map('gD', vim.lsp.buf.declaration, opt, "Go to declaration")
  map('gd', vim.lsp.buf.definition, opt, "Go to definition")
  map('gi', vim.lsp.buf.implementation, opt, "Go to implementation")

  map('K', vim.lsp.buf.hover, opt, "Hover text")
  map('<C-k>', vim.lsp.buf.signature_help, opt, "Show signature")

  map('<space>wa', vim.lsp.buf.add_workspace_folder, opt, "Add workspace folder")
  map('<space>wr', vim.lsp.buf.remove_workspace_folder, opt, "Remove workspace folder")
  map('<space>wl', function()
    print(vim.inspect(vim.lsp.buf.list_workspace_folders()))
  end, opt, "List workspace folders")

  map('<space>D', vim.lsp.buf.type_definition, opt, "Go to type definition")
  map('<space>rn', vim.lsp.buf.rename, opt, "Rename")
  map('<space>ca', vim.lsp.buf.code_action, opt, "Code actions")
  vim.keymap.set('v', "<space>ca", "<ESC><CMD>lua vim.lsp.buf.range_code_action()<CR>", { noremap=true, silent=true, buffer=bufnr, desc = "Code actions" })
  map('<space>f', function() vim.lsp.buf.format { async = true } end, opt, "Format file")

  -- Java extensions provided by jdtls
  map("<space>co", jdtls.organize_imports, opt, "Organize imports")
  map("<space>ev", jdtls.extract_variable, opt, "Extract variable")
  map("<space>ec", jdtls.extract_constant, opt, "Extract constant")
  vim.keymap.set('v', "<space>em", [[<ESC><CMD>lua require('jdtls').extract_method(true)<CR>]],
    { noremap=true, silent=true, buffer=bufnr, desc = "Extract method" })
end

jdtls.start_or_attach {
  on_attach = on_attach,
  root_dir = root_dir,
  workspace_folder = workspace_folder,

  flags = {
    debounce_text_changes = 80,
  },

  filetypes = { "java", "groovy" },
  settings = {
    java = {
      format = {
        settings = {
          url = "/.local/share/eclipse/eclipse-java-google-style.xml",
          profile = "GoogleStyle",
        },
      },
      signatureHelp = { enabled = true },
      contentProvider = { preferred = 'fernflower' },
      completion = {
        favoriteStaticMembers = {
          'org.assertj.core.api.Assertions.assertThat',
          'org.assertj.core.api.Assertions.*',
          "org.mockito.Mockito.*"
        },
        filteredTypes = {
          "com.sun.*",
          "io.micrometer.shaded.*",
          "java.awt.*",
          "jdk.*",
          "sun.*",
        },
      },
      -- Specify any options for organizing imports

      imports = {
        order = {
          "com",              -- Com imports
          "org",              -- Org imports
          "java",             -- Regular Java imports
          "#",                -- Static imports (indicated by "#")
        },
        staticGroups = true, -- Place static imports last
      },

      sources = {
        organizeImports = {
          starThreshold = 9999;
          staticStarThreshold = 9999;
        },
      },
      -- How code generation should act
      codeGeneration = {
        toString = {
          template = "${object.className}{${member.name()}=${member.value}, }",
          useFullyQualifiedNames = false,
          skipNullValues = false,
          listArrayContents = true,
        },
        hashCodeEquals = {
          useJava7Objects = true,
        },
        useBlocks = true,
      },
      -- If you are developing in projects with different Java versions, you need
      -- to tell eclipse.jdt.ls to use the location of the JDK for your Java version
      -- See https://github.com/eclipse/eclipse.jdt.ls/wiki/Running-the-JAVA-LS-server-from-the-command-line#initialize-request
      -- And search for `interface RuntimeOption`
      -- The `name` is NOT arbitrary, but must match one of the elements from `enum ExecutionEnvironment` in the link above
      configuration = {
        runtimes = {
          {
            name = "java",
            path = vim.fn.getenv "JAVA_VERSION",
          }
        }
      }
    }
  },

  cmd = {
    'java',
    '-Declipse.application=org.eclipse.jdt.ls.core.id1',
    '-Dosgi.bundles.defaultStartLevel=4',
    '-Declipse.product=org.eclipse.jdt.ls.core.product',
    '-Dlog.level=ALL',
    '-noverify',
    '-Xmx4G',
    '-jar', vim.fn.glob('/opt/homebrew/Cellar/jdtls/1.*.0/libexec/plugins/org.eclipse.equinox.launcher_*.jar'),
    '-configuration', vim.fn.glob('/opt/homebrew/Cellar/jdtls/1.*.0/libexec/config_mac'),
    '-data', workspace_folder,
  },
}

