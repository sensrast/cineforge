PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS queue (
 id INTEGER PRIMARY KEY AUTOINCREMENT, movie_name TEXT NOT NULL, search_query TEXT NOT NULL,
 content_type TEXT NOT NULL DEFAULT 'movie',
 status TEXT NOT NULL DEFAULT 'pending', current_stage INTEGER NOT NULL DEFAULT 0,
 error_message TEXT, retry_count INTEGER NOT NULL DEFAULT 0, requested_by INTEGER,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_queue_pick ON queue(status, created_at);
CREATE TABLE IF NOT EXISTS pipeline_state (
 queue_id INTEGER PRIMARY KEY REFERENCES queue(id) ON DELETE CASCADE,
 source_messages_json TEXT DEFAULT '[]', filtered_files_json TEXT DEFAULT '[]', fetched_files_json TEXT DEFAULT '[]',
 channel_id INTEGER, invite_link TEXT, owner_promoted INTEGER DEFAULT 0, forwarded_message_ids_json TEXT DEFAULT '[]',
 batch_link TEXT, shortened_link TEXT, final_post_id INTEGER, catalog_added INTEGER DEFAULT 0,
 updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS created_channels (
 id INTEGER PRIMARY KEY AUTOINCREMENT, queue_id INTEGER REFERENCES queue(id), movie_name TEXT NOT NULL,
 content_type TEXT NOT NULL DEFAULT 'movie', channel_id INTEGER UNIQUE, invite_link TEXT, batch_link TEXT, shortened_link TEXT,
 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY AUTOINCREMENT, queue_id INTEGER, level TEXT DEFAULT 'INFO', message TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS daily_stats (date TEXT PRIMARY KEY, channels_created INTEGER DEFAULT 0, floodwait_hits INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
INSERT OR IGNORE INTO settings(key,value) VALUES
 ('limits_enabled','false'),('delay_between_actions','0.0'),('delay_between_movies','0.0'),
 ('max_channels_per_day','0'),('desired_qualities','480p,720p,1080p,2160p,4K'),
 ('language_filter','Hindi'),('search_strategy','First Matching Page'),('max_search_pages','32'),('source_timeout','30'),('flow_timeout','60'),
 ('default_genre','Action'),('catalog_language','Hindi'),
 ('auto_catalog','true'),('pipeline_paused','false');
