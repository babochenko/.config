local M = {}

local bin = vim.fn.expand(vim.g.opendash_bin or '~/.config/opendash/opendash')
local cache = { cwd = nil, value = {}, selected = nil, busy = false }
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
      cache.cwd, cache.value, cache.selected = dir, {}, nil
      vim.cmd('redrawstatus')
      return
    end
    local ok, value = pcall(vim.json.decode, result.stdout)
    if value == vim.NIL then value = nil end
    cache.cwd, cache.value = dir, ok and value or {}
    if type(cache.value) ~= 'table' then cache.value = {} end
    vim.cmd('redrawstatus')
  end)
end

local function current(callback)
  local dir = cwd()
  if cache.cwd == dir and cache.value and #cache.value > 0 then
    callback(cache.value)
    return
  end
  run({ 'agent', dir }, function(result)
    if result.code ~= 0 then
      callback({})
      return
    end
    local ok, value = pcall(vim.json.decode, result.stdout)
    if value == vim.NIL then value = nil end
    cache.cwd, cache.value = dir, ok and value or {}
    if type(cache.value) ~= 'table' then cache.value = {} end
    callback(cache.value)
  end)
end

local function context(visual)
  local filename = vim.fn.expand('%:p')
  if filename == '' then filename = '[No Name]' end
  local details = { 'Current file: ' .. filename }
  if visual then
    local first = math.min(vim.fn.line("'<"), vim.fn.line("'>"))
    local last = math.max(vim.fn.line("'<"), vim.fn.line("'>"))
    local lines = vim.fn.getline(first, last)
    table.insert(details, string.format('Selected lines %d-%d:', first, last))
    for index, line in ipairs(lines) do
      table.insert(details, string.format('%d: %s', first + index - 1, line))
    end
  end
  return table.concat(details, '\n')
end

function M.chat(visual)
  local prompt_context = context(visual)
  current(function(agents)
    if #agents == 0 then
      vim.notify('no opendash agent for ' .. cwd(), vim.log.levels.INFO)
      return
    end
    local function ask(agent)
      cache.selected = agent.session_id
      vim.ui.input({ prompt = agent.agent_name .. ' > ' }, function(text)
        if not text or vim.trim(text) == '' then return end
        vim.notify(agent.agent_name .. ': sending...', vim.log.levels.INFO)
        local prompt = text .. '\n\nContext:\n' .. prompt_context
        run({ 'prompt', agent.session_id, prompt }, function(result)
          if result.code == 0 then
            refresh()
          else
            vim.notify(vim.trim(result.stderr), vim.log.levels.ERROR)
          end
        end)
      end)
    end
    if #agents == 1 then
      ask(agents[1])
    else
      vim.ui.select(agents, {
        prompt = 'opendash agent:',
        format_item = function(agent)
          return string.format('%s  %s  %s', agent.agent_name, agent.state or 'unknown',
            vim.trim(agent.preview or ''))
        end
      }, function(agent)
        if agent then ask(agent) end
      end)
    end
  end)
end

function M.statusline()
  local agents = cache.cwd == cwd() and cache.value or {}
  local agent
  for _, candidate in ipairs(agents) do
    if candidate.session_id == cache.selected then agent = candidate end
  end
  if not agent and #agents == 1 then agent = agents[1] end
  if not agent then
    if #agents > 1 then return string.format('%d opendash agents', #agents) end
    return ''
  end
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
