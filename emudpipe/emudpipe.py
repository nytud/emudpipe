#!/usr/bin/env python3
# -*- coding: utf-8, vim: expandtab:ts=4 -*-

import os
from collections import namedtuple

# Install this.
# !pip install ufal.udpipe

# Load this
from ufal.udpipe import Model, Pipeline, ProcessingError


class UDPipeError(Exception):
    pass


class UDPipe:
    conll_line = namedtuple('CoNLL', 'id, form, lemma, upostag, xpostag, feats, head, deprel, deps, misc')

    def __init__(self, task='parse', model=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                        'hungarian-szeged-ud-2.4-190531.udpipe'),
                 source_fields=None, target_fields=None):
        # Download model: https://lindat.mff.cuni.cz/repository/xmlui/handle/11234/1-2898
        self._model = Model.load(model)  # Load this
        if self._model is None:
            raise UDPipeError('ERROR:Loading modelfile {0}'.format(model))
        available_tasks = {'tok': self._setup_tok, 'pos': self._setup_pos, 'parse': self._setup_parse,
                           'tok-pos': self._setup_tok_pos, 'tok-parse': self._setup_tok_parse,
                           'pos-parse': self._setup_pos_parse}

        for keyword, key_fun in available_tasks.items():
            if task == keyword:
                key_fun()  # Do setup!
                self._task = task  # Store for later
                break
        else:
            raise ValueError('No proper task is specified. The available tasks are {0}'.
                             format(' or '.join(available_tasks.keys())))

        # Field names for xtsv (the code below is mandatory for an xtsv module)
        if source_fields is None:
            source_fields = set()

        if target_fields is None:
            target_fields = []

        self.source_fields = source_fields
        self.target_fields = target_fields

    def _setup_tok(self):
        self._inp_format = 'tokenize'
        self._pos_settings = Pipeline.NONE
        self._parse_settings = Pipeline.NONE
        self._ret_field_names = lambda field_names: field_names
        self._encode_sentence = lambda x, _: x  # Raw text passed as is
        self._decode_sentence = self._decode_sentence_tok

    def _setup_pos(self):
        self._inp_format = 'conllu'
        self._pos_settings = Pipeline.DEFAULT
        self._parse_settings = Pipeline.NONE
        self._ret_field_names = lambda field_names: [field_names['form']]
        self._encode_sentence = self._encode_sentence
        self._decode_sentence = self._decode_sentence_conlu

    def _setup_parse(self):
        self._inp_format = 'conllu'
        self._pos_settings = Pipeline.NONE
        self._parse_settings = Pipeline.DEFAULT
        self._ret_field_names = lambda field_names: [field_names['form'], field_names['lemma'],
                                                     field_names['upostag'], field_names['feats']]
        self._encode_sentence = self._encode_sentence
        self._decode_sentence = self._decode_sentence_conlu

    def _setup_tok_pos(self):
        self._inp_format = 'tokenize'
        self._pos_settings = Pipeline.DEFAULT
        self._parse_settings = Pipeline.NONE
        self._ret_field_names = lambda field_names: field_names
        self._encode_sentence = lambda x, _: x  # Raw text passed as is
        self._decode_sentence = self._decode_sentence_tok

    def _setup_tok_parse(self):
        self._inp_format = 'tokenize'
        self._pos_settings = Pipeline.DEFAULT
        self._parse_settings = Pipeline.DEFAULT
        self._ret_field_names = lambda field_names: field_names
        self._encode_sentence = lambda x, _: x  # Raw text passed as is
        self._decode_sentence = self._decode_sentence_tok

    def _setup_pos_parse(self):
        self._inp_format = 'conllu'
        self._pos_settings = Pipeline.DEFAULT
        self._parse_settings = Pipeline.DEFAULT
        self._ret_field_names = lambda field_names: [field_names['form']]
        self._encode_sentence = self._encode_sentence
        self._decode_sentence = self._decode_sentence_conlu

    @staticmethod
    def _encode_sentence(inp_sen, field_names):
        out_lines = []
        for i, inp_tok in enumerate(inp_sen, start=1):
            source_fields = []
            for field in ('lemma', 'upostag', 'feats'):
                field_ind = field_names.get(field)
                if field_ind is not None and len(inp_tok) > field_ind:
                    field_val = inp_tok[field_ind]
                else:
                    field_val = '_'
                source_fields.append(field_val)

            tok = [
                str(i),  # ID
                inp_tok[field_names['form']],  # FORM
                source_fields[0],  # LEMMA
                source_fields[1],  # UPOSTAG
                '_',  # XPOSTAG
                source_fields[2],  # FEATS
                '_',  # HEAD
                '_',  # DEPREL
                '_',  # DEPS
                '_',  # MISC
            ]
            out_lines.append('\t'.join(tok))

        return '\n'.join(out_lines)

    def _decode_sentence_tok(self, processed, *_):  # tok, tok-pos, tok-parse
        for line in processed.split('\n'):
            if len(line) == 0:
                yield '\n'
            elif line.startswith('#'):
                pass
            else:
                fields = self.conll_line._make(line.split('\t'))
                tf = set(self.target_fields)
                # TODO: join should be in TSV handler!
                yield '{0}\n'.format('\t'.join([v for k, v in fields._asdict().items() if k in tf]))

    def _decode_sentence_conlu(self, processed, sen, field_names):  # pos, pos-parse, parse
        for line in processed.split('\n'):
            if len(line) == 0 or line.startswith('#'):
                pass
            else:
                fields = self.conll_line._make(line.split('\t'))
                fields_dict = fields._asdict()
                sf = self.source_fields
                tok_id = int(fields_dict['id']) - 1
                curr_tok = sen[tok_id]

                # Sanity check! (1) Header check,
                # (2) Source fields equality check (eg. source fields have not been modified or retokenised)
                assert sf.issubset(fields_dict.keys())
                assert all([curr_tok[field_names[field_name]] == field_value
                            for field_name, field_value in fields_dict.items() if field_name in sf])
                curr_tok.extend([fields_dict[field_name] for field_name in self.target_fields])

        return sen

    @staticmethod
    def prepare_fields(field_names):
        return field_names  # These needed by name for the decoding

    def process_sentence(self, sen, field_names=None):
        pipeline = Pipeline(self._model, self._inp_format, self._pos_settings, self._parse_settings, 'conllu')
        error = ProcessingError()  # For catching errors...

        inp_sen = ''.join(self._encode_sentence(sen, field_names))
        # Do the processing... + Write the output in CoNLL-U
        processed = pipeline.process(inp_sen, error)

        if error.occurred():
            raise UDPipeError(error.message)

        ret_sen = self._decode_sentence(processed, sen, field_names)
        return ret_sen
