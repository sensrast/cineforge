from telegram import InlineKeyboardButton,InlineKeyboardMarkup
def settings_keyboard(values:dict[str,str])->InlineKeyboardMarkup:
 enabled=values.get('limits_enabled','false')=='true'; auto=values.get('auto_catalog','true')=='true'
 return InlineKeyboardMarkup([
  [InlineKeyboardButton(f'Limits: {"ON" if enabled else "OFF"}',callback_data='cfg:toggle:limits_enabled')],
  [InlineKeyboardButton(f'Action delay: {values.get("delay_between_actions","0")}s',callback_data='cfg:set:delay_between_actions'),InlineKeyboardButton(f'Movie delay: {values.get("delay_between_movies","0")}s',callback_data='cfg:set:delay_between_movies')],
  [InlineKeyboardButton(f'Max channels/day: {values.get("max_channels_per_day","0")}',callback_data='cfg:set:max_channels_per_day')],
  [InlineKeyboardButton(f'Auto catalog: {"ON" if auto else "OFF"}',callback_data='cfg:toggle:auto_catalog')],
 ])
