# coding=utf-8
# Copyright 2019 The Google AI Language Team Authors and Masatoshi Suzuki.
# Copyright (c) 2018, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# This file is based on the following files:
# [1] https://github.com/google-research/bert/blob/master/tokenization.py
"""Tokenization classes for BERT Japanese models."""

import collections
import logging
import os
import unicodedata

import tensorflow as tf


logger = logging.getLogger(__name__)


def load_vocab(vocab_file):
    """Loads a vocabulary file into a dictionary."""
    vocab = collections.OrderedDict()
    index = 0
    with tf.gfile.GFile(vocab_file, 'r') as reader:
        for line in reader:
            token = line.strip()
            vocab[token] = index
            index += 1

    return vocab


def whitespace_tokenize(text):
    """Runs basic whitespace cleaning and splitting on a piece of text."""
    text = text.strip()
    if not text:
        return []

    tokens = text.split()
    return tokens


class MecabBasicTokenizer(object):
    """Runs basic tokenization with MeCab morphological parser."""

    def __init__(self, do_lower_case=False, dict_path=None):
        """Constructs a BasicTokenizer.
        Args:
            do_lower_case: Whether to lower case the input.
        """

        self.do_lower_case = do_lower_case
        self.dict_path = dict_path
        import MeCab
        if dict_path:
            self.mecab = MeCab.Tagger('-d {}'.format(dict_path))
        else:
            self.mecab = MeCab.Tagger()

    def tokenize(self, text):
        """Tokenizes a piece of text."""

        tokens = []
        token_infos = []
        for line in self.mecab.parse(text).split('\n'):
            if line == 'EOS':
                break

            token, token_info = line.split('\t')
            token = token.strip()
            if not token:
                continue

            if self.do_lower_case:
                token = token.lower()

            tokens.append(token)
            token_infos.append(token_info)

        assert len(tokens) == len(token_infos)
        return tokens, token_infos


class WordpieceTokenizer(object):
    """Runs WordPiece tokenziation."""

    def __init__(self, vocab, unk_token='[UNK]', max_input_chars_per_word=200):
        self.vocab = vocab
        self.unk_token = unk_token
        self.max_input_chars_per_word = max_input_chars_per_word

    def tokenize(self, text):
        """Tokenizes a piece of text into its word pieces.
        This uses a greedy longest-match-first algorithm to perform tokenization
        using the given vocabulary.
        For example:
            input = "unaffable"
            output = ["un", "##aff", "##able"]
        Args:
            text: A single token or whitespace separated tokens. This should have
                already been passed through `BasicTokenizer.
        Returns:
            A list of wordpiece tokens.
        """

        output_tokens = []
        for token in whitespace_tokenize(text):
            chars = list(token)
            if len(chars) > self.max_input_chars_per_word:
                output_tokens.append(self.unk_token)
                continue

            is_bad = False
            start = 0
            sub_tokens = []
            while start < len(chars):
                end = len(chars)
                cur_substr = None
                while start < end:
                    substr = "".join(chars[start:end])
                    if start > 0:
                        substr = "##" + substr

                    if substr in self.vocab:
                        cur_substr = substr
                        break

                    end -= 1

                if cur_substr is None:
                    is_bad = True
                    break

                sub_tokens.append(cur_substr)
                start = end

            if is_bad:
                output_tokens.append(self.unk_token)
            else:
                output_tokens.extend(sub_tokens)

        return output_tokens


class MecabBertTokenizer(object):
    """Runs end-to-end tokenization: MeCab tokenization + wordpiece"""

    def __init__(self, vocab_file, do_lower_case=False, dict_path=None,
                 never_split=('[UNK]', '[SEP]', '[PAD]', '[CLS]', '[MASK]')):
        """Constructs a BertTokenizer.
        Args:
            vocab_file: Path to a one-wordpiece-per-line vocabulary file.
            do_lower_case: Whether to lower case the input.
            dict_path: Path to a MeCab custom dictionary.
            never_split: List of tokens which will never be split during tokenization.
        """
        self.vocab = load_vocab(vocab_file)
        self.ids_to_tokens = collections.OrderedDict(
            [(ids, tok) for tok, ids in self.vocab.items()])
        self.never_split = never_split
        self.mecab_tokenizer = MecabBasicTokenizer(do_lower_case, dict_path)
        self.wordpiece_tokenizer = WordpieceTokenizer(self.vocab)

    def tokenize(self, text, with_info=False):
        output_tokens = []
        output_token_infos = []

        text = unicodedata.normalize('NFKC', text)
        for token in self.never_split:
            text = text.replace(token, '\n{}\n'.format(token))

        texts = text.split('\n')
        for text in texts:
            if text in self.never_split:
                output_tokens.append(text)
                output_token_infos.append(None)
                continue

            for token, token_info in zip(self.mecab_tokenizer.tokenize(text)):
                for i, sub_token in enumerate(self.wordpiece_tokenizer.tokenize(token)):
                    output_tokens.append(sub_token)
                    if i == 0:
                        output_token_infos.append(token_info)
                    else:
                        output_token_infos.append(None)

        assert len(output_tokens) == len(output_token_infos)
        if with_info:
            return output_tokens, output_token_infos
        else:
            return output_tokens

    def convert_tokens_to_ids(self, tokens):
        """Converts a sequence of tokens into ids using the vocab."""
        ids = []
        for token in tokens:
            ids.append(self.vocab[token])

        return ids

    def convert_ids_to_tokens(self, ids):
        """Converts a sequence of ids in wordpiece tokens using the vocab."""
        tokens = []
        for i in ids:
            tokens.append(self.ids_to_tokens[i])

        return tokens


class CharacterBertTokenizer(object):
    """Runs character tokenization"""

    def __init__(self, vocab_file, do_lower_case=False,
                 never_split=('[UNK]', '[SEP]', '[PAD]', '[CLS]', '[MASK]')):
        """Constructs a BertTokenizer.
        Args:
            vocab_file: Path to a one-wordpiece-per-line vocabulary file.
            do_lower_case: Whether to lower case the input.
            never_split: List of tokens which will never be split during tokenization.
        """
        self.vocab = load_vocab(vocab_file)
        self.do_lower_case = do_lower_case
        self.ids_to_tokens = collections.OrderedDict(
            [(ids, tok) for tok, ids in self.vocab.items()])
        self.never_split = never_split

    def tokenize(self, text):
        output_tokens = []

        text = unicodedata.normalize('NFKC', text)
        for token in self.never_split:
            text = text.replace(token, '\n{}\n'.format(token))

        texts = text.split('\n')
        for text in texts:
            if text in self.never_split:
                output_tokens.append(text)
                continue

            if self.do_lower_case:
                text = text.lower

            output_tokens.extend(text)

        return output_tokens

    def convert_tokens_to_ids(self, tokens):
        """Converts a sequence of tokens into ids using the vocab."""
        ids = []
        for token in tokens:
            ids.append(self.vocab[token])

        return ids

    def convert_ids_to_tokens(self, ids):
        """Converts a sequence of ids in wordpiece tokens using the vocab."""
        tokens = []
        for i in ids:
            tokens.append(self.ids_to_tokens[i])

        return tokens
