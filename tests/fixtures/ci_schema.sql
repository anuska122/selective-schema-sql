CREATE TABLE public.colour (
    id bigint PRIMARY KEY,
    colour text
);

CREATE TABLE public.superhero (
    id bigint PRIMARY KEY,
    superhero_name text,
    skin_colour_id bigint REFERENCES public.colour (id)
);

CREATE SEQUENCE public.cards_id_seq;

CREATE TABLE public.cards (
    id bigint PRIMARY KEY DEFAULT nextval('public.cards_id_seq'),
    name text
);

INSERT INTO public.colour VALUES (1, 'No Colour'), (2, 'Green');
INSERT INTO public.superhero VALUES (1, 'A-Bomb', 1), (2, 'Abe Sapien', 2);
INSERT INTO public.cards (name) VALUES ('Ancestor''s Chosen');
