PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS queue (
 id INTEGER PRIMARY KEY AUTOINCREMENT, movie_name TEXT NOT NULL, search_query TEXT NOT NULL,
 content_type TEXT NOT NULL DEFAULT 'movie', force_rebuild INTEGER NOT NULL DEFAULT 0,
 input_mode TEXT NOT NULL DEFAULT 'automatic',
 status TEXT NOT NULL DEFAULT 'pending', current_stage INTEGER NOT NULL DEFAULT 0,
 error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0, requested_by INTEGER,
 next_attempt_at TIMESTAMP,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_queue_pick ON queue(status, created_at);
CREATE TABLE IF NOT EXISTS pipeline_state (
 queue_id INTEGER PRIMARY KEY REFERENCES queue(id) ON DELETE CASCADE,
 source_messages_json TEXT DEFAULT '[]', filtered_files_json TEXT DEFAULT '[]', fetched_files_json TEXT DEFAULT '[]',
 channel_id INTEGER, invite_link TEXT, owner_promoted INTEGER DEFAULT 0, forwarded_message_ids_json TEXT DEFAULT '[]',
 batch_link TEXT, shortened_link TEXT, final_post_id INTEGER, catalog_added INTEGER DEFAULT 0,
 backup_done INTEGER DEFAULT 0, backup_message_ids_json TEXT DEFAULT '[]',
 promotion_done INTEGER DEFAULT 0, promotion_link TEXT, promotion_post_id INTEGER, promotion_sticker_id INTEGER,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS created_channels (
 id INTEGER PRIMARY KEY AUTOINCREMENT, queue_id INTEGER REFERENCES queue(id), movie_name TEXT NOT NULL,
 content_type TEXT NOT NULL DEFAULT 'movie', channel_id INTEGER UNIQUE, invite_link TEXT, batch_link TEXT, shortened_link TEXT,
 owner_admin_confirmed INTEGER DEFAULT 0,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, queue_id INTEGER, level TEXT DEFAULT 'INFO', message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS daily_stats (date TEXT PRIMARY KEY, channels_created INTEGER DEFAULT 0, floodwait_hits INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS manual_upload_sessions (
 owner_id INTEGER PRIMARY KEY, content_type TEXT NOT NULL DEFAULT 'movie', title TEXT,
 status TEXT NOT NULL DEFAULT 'awaiting_title', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS manual_upload_files (
 id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
 file_unique_id TEXT NOT NULL, file_size INTEGER NOT NULL DEFAULT 0, file_name TEXT, caption TEXT,
 explicit_quality TEXT, season INTEGER, episode INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(owner_id,file_unique_id)
);
CREATE TABLE IF NOT EXISTS mirror_sources (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_chat_id INTEGER UNIQUE NOT NULL, source_ref TEXT,
 source_title TEXT NOT NULL, destination_chat_id INTEGER, invite_link TEXT,
 status TEXT NOT NULL DEFAULT 'awaiting_confirmation', current_season INTEGER DEFAULT 0,
 current_episode INTEGER DEFAULT 0, last_source_message_id INTEGER DEFAULT 0,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS mirror_season_stickers (
 source_id INTEGER NOT NULL REFERENCES mirror_sources(id) ON DELETE CASCADE,
 season INTEGER NOT NULL, sticker_file_id TEXT NOT NULL, PRIMARY KEY(source_id,season)
);
CREATE TABLE IF NOT EXISTS mirror_seen (
 source_id INTEGER NOT NULL REFERENCES mirror_sources(id) ON DELETE CASCADE,
 source_message_id INTEGER NOT NULL, PRIMARY KEY(source_id,source_message_id)
);
CREATE TABLE IF NOT EXISTS mirror_pending (
 id INTEGER PRIMARY KEY AUTOINCREMENT, source_id INTEGER NOT NULL REFERENCES mirror_sources(id) ON DELETE CASCADE,
 source_message_id INTEGER NOT NULL, season INTEGER NOT NULL, episode INTEGER NOT NULL,
 quality TEXT, file_size INTEGER DEFAULT 0, file_name TEXT, added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(source_id,source_message_id)
);
INSERT OR IGNORE INTO settings(key,value) VALUES
 ('limits_enabled','false'),('delay_between_actions','0.0'),('delay_between_movies','0.0'),
 ('max_channels_per_day','0'),('desired_qualities','480p,720p,1080p,2160p,4K'),
 ('language_filter','Hindi'),('search_strategy','First Matching Page'),('max_search_pages','32'),('source_timeout','30'),('flow_timeout','60'),
 ('floodwait_defer_threshold','120'),('owner_admin_reconcile_interval','60'),
 ('default_genre','Action'),('catalog_language','Hindi'),
 ('backup_enabled','false'),('backup_channel',''),
 ('promotion_enabled','false'),('promotion_updates_channel','@In_hindi_dubbed_movies'),
 ('promotion_link_provider','Yclinkproviderbot'),
 ('promotion_caption','<b>❤️‍🔥 {movie}</b>\n\n<blockquote><b>🥳 all qualities Added ....!🕺</b></blockquote>'),
 ('promotion_button_text','Click here to start and get Movie'),
 ('promotion_updates_sticker',''),('created_channels_folder_enabled','true'),
 ('created_channels_folder_name','🎬 Movie Channels'),
 ('auto_catalog','true'),('pipeline_paused','false');
