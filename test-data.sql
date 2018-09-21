INSERT INTO question(text_value) VALUES ('Question 1');
INSERT INTO variant(variant_id, question_id, text_value, correct) VALUES
    ('A', 1, 'Correct Answer', true),
    ('B', 1, 'Incorrect Answer', false),
    ('C', 1, 'Incorrect Answer', false),
    ('D', 1, 'Incorrect Answer', false);

INSERT INTO question(text_value) VALUES ('Question 2 - 5 answers');
INSERT INTO variant(variant_id, question_id, text_value, correct) VALUES
    ('A', 2, 'Incorrect Answer', false),
    ('B', 2, 'Incorrect Answer', false),
    ('C', 2, 'Incorrect Answer', false),
    ('D', 2, 'Incorrect Answer', false),
    ('E', 2, 'Correct Answer', true);

INSERT INTO question(text_value) VALUES ('Question 3 - 3 answers');
INSERT INTO variant(variant_id, question_id, text_value, correct) VALUES
    ('A', 3, 'Incorrect Answer', false),
    ('B', 3, 'Correct Answer', true),
    ('C', 3, 'Incorrect Answer', false);

INSERT INTO player(player_id, player_name, chat_id, registration_time) VALUES
    ('one', 'one', 1, current_timestamp),
    ('two', 'two', 2, current_timestamp),
    ('three', 'three', 3, current_timestamp),
    ('four', 'four', 4, current_timestamp),
    ('five', 'five', 5, current_timestamp),
    ('six', 'six', 6, current_timestamp),
    ('seven', 'seven', 7, current_timestamp),
    ('eight', 'eight', 8, current_timestamp),
    ('nine', 'nine', 9, current_timestamp),
    ('ten', 'ten', 10, current_timestamp),
    ('eleven', 'eleven', 11, current_timestamp),
    ('twelve', 'twelve', 12, current_timestamp);

INSERT INTO hint(player_id, question_id, hint_key, tries) VALUES
    ('two', 1, 'test_hint', 1);

INSERT INTO answer(player_id, question_id, variant_id, tries, passed, answer_time) VALUES
-- expected rating: four, five, three, two, one, seven, six
--   has +1 tries
    ('one', 1, 'A', 1, true, current_timestamp - interval '1 day'),
    ('one', 2, 'E', 2, true, current_timestamp - interval '1 day'),
--   used hint
    ('two', 1, 'A', 1, true, current_timestamp),
    ('two', 2, 'E', 1, true, current_timestamp),
--   answered later
    ('three', 1, 'A', 1, true, current_timestamp),
    ('three', 2, 'E', 1, true, current_timestamp),
--  leader
    ('four', 1, 'A', 1, true, current_timestamp - interval '2 days'),
    ('four', 2, 'E', 1, true, current_timestamp - interval '2 days'),
--  answered earlier
    ('five', 1, 'A', 1, true, current_timestamp - interval '1 day'),
    ('five', 2, 'E', 1, true, current_timestamp - interval '1 day'),
--  failed last answer, answered later
    ('six', 1, 'A', 1, true, current_timestamp),
    ('six', 2, 'E', 1, true, current_timestamp),
--  no last answer
    ('seven', 1, 'A', 1, true, current_timestamp - interval '1 day');
