return {

  copy_file_path = function()
    local path = vim.fn.expand("%:p")
    vim.fn.setreg("+", path)
    print(path)
  end,

  copy_file_name = function()
    local file = vim.fn.expand("%:t")
    vim.fn.setreg("+", file)
    print(file)
  end,

  toggle_mouse = function()
    if vim.o.mouse == 'a' then
      vim.o.mouse = ''
      print('Mouse disabled')
    else
      vim.o.mouse = 'a'
      print('Mouse enabled')
    end
  end,

  open_system = function()
    local file_path = vim.fn.expand("%:p") -- Get the full path of the current file
    if file_path == "" then
      print("No file is currently open.")
      return
    end

    -- Command for macOS, Linux, or Windows
    local command
    if vim.fn.has("mac") == 1 then
      command = "open " .. vim.fn.shellescape(file_path)
    elseif vim.fn.has("unix") == 1 then
      command = "xdg-open " .. vim.fn.shellescape(file_path)
    elseif vim.fn.has("win32") == 1 then
      command = "start " .. vim.fn.shellescape(file_path)
    else
      print("Unsupported system.")
      return
    end

    -- Execute the command
    vim.fn.system(command)
    print("Opened file in system editor: " .. file_path)
  end,

}

