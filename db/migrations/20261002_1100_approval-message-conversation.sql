-- An approval's message must belong to the approval's conversation.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'messages_id_conversation_uq') then
        alter table messages add constraint messages_id_conversation_uq unique (id, conversation_id);
    end if;
    if not exists (select 1 from pg_constraint where conname = 'approvals_message_conversation_fk') then
        alter table approvals add constraint approvals_message_conversation_fk
            foreign key (message_id, conversation_id) references messages (id, conversation_id)
            on delete restrict;
    end if;
end $$;
