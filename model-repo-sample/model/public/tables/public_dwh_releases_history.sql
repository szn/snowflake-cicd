create table public.dwh_releases_history (
	commit varchar(40) not null,
	file_name varchar(255) not null,
	installed_by varchar(100) not null default current_user(),
	installed_on timestamp_ltz(9) not null default current_timestamp(),
	primary key (commit)
);

insert into public.dwh_releases_history (
	commit,
	file_name,
	installed_by
) values (
	'1f176372d273eec903c75d0860d96edf02472ca0',
	'<<init>>',
	'szymon.nieradka@qliro.com'
);
