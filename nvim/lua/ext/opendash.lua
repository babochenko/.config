local M = {}

local bin = vim.fn.expand(vim.g.opendash_bin or '~/.config/opendash/opendash')
local cache = { cwd = nil, value = nil, busy = false }
local spinner = { '⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏' }

local function cwd()
  return vim.fn.getcwd()
end

local function run(args, callback)
  local command = vim.list_extend({ bin }, args)
  vim.system(command, { text = true }, function(result)
    vim.schedule(function()
      callback(result)
    end)
  end)
end

local function refresh()
  if cache.busy then return end
  cache.busy = true
  local dir = cwd()
  run({ 'agent', dir }, function(result)
    cache.busy = false
    if result.code ~= 0 then
      cache.cwd, cache.value = dir, nil
      vim.cmd('redrawstatus')
      return
    end
    local ok, value = pcall(vim.json.decode, result.stdout)
    if value == vim.NIL then value = nil end
    cache.cwd, cache.value = dir, ok and value or nil
    vim.cmd('redrawstatus')
  end)
end

local function current(callback)
  local dir = cwd()
  if cache.cwd == dir and cache.value then
    callback(cache.value)
    return
  end
  run({ 'agent', dir }, function(result)
    if result.code ~= 0 then
      callback(nil)
      return
    end
    local ok, value = pcall(vim.json.decode, result.stdout)
    if value == vim.NIL then value = nil end
    cache.cwd, cache.value = dir, ok and value or nil
    callback(cache.value)
  end)
end

function M.chat()
  current(function(agent)
    if not agent then
      vim.notify('no opendash agent for ' .. cwd(), vim.log.levels.INFO)
      return
    end
    vim.ui.input({ prompt = agent.agent_name .. ' > ' }, function(text)
      if not text or vim.trim(text) == '' then return end
      vim.notify(agent.agent_name .. ': sending...', vim.log.levels.INFO)
      run({ 'prompt', agent.session_id, text }, function(result)
        if result.code == 0 then
          refresh()
        else
          vim.notify(vim.trim(result.stderr), vim.log.levels.ERROR)
        end
      end)
    end)
  end)
end

function M.statusline()
  local agent = cache.cwd == cwd() and cache.value or nil
  if not agent then return '' end
  local state = agent.state or 'unknown'
  local icon = state == 'working' and spinner[(math.floor(vim.loop.hrtime() / 1e8) % #spinner) + 1]
    or ({ idle = '●', queued = '◔', error = '✖', attention = '◆' })[state] or '○'
  local preview = vim.trim(agent.preview or ''):gsub('[\r\n]+', ' ')
  if #preview > 60 then preview = preview:sub(1, 57) .. '...' end
  return string.format('%s %s %s', agent.agent_name or 'default', icon, preview)
end

function M.setup()
  refresh()
  local timer = vim.uv.new_timer()
  timer:start(1500, 1500, vim.schedule_wrap(refresh))
  vim.api.nvim_create_autocmd('DirChanged', { callback = refresh })
  vim.api.nvim_create_autocmd('VimLeavePre', {
    callback = function()
      if not timer:is_closing() then timer:stop(); timer:close() end
    end,
  })
end

return M
