return {
    open_config_file = function()
      vim.cmd("edit " .. vim.fn.stdpath("state") .. "/dbee/persistence.json")
    end,
}

