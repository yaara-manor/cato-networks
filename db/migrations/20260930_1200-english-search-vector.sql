-- Startup re-applies every migration file on each pg_restore, so this guard
-- checks the stored expression first: an unguarded SET EXPRESSION would
-- rewrite all 14k passage rows on every start.
do $$
begin
    if (
        select pg_get_expr(adbin, adrelid)
        from pg_attrdef
        join pg_attribute
            on pg_attribute.attrelid = pg_attrdef.adrelid
            and pg_attribute.attnum = pg_attrdef.adnum
        where pg_attrdef.adrelid = 'passages'::regclass
            and pg_attribute.attname = 'search_vector'
    ) like '%simple%' then
        alter table passages
            alter column search_vector set expression as (to_tsvector('english', body));
    end if;
end
$$;
