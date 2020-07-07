import os
import sys

from gensim.corpora import Dictionary
from nltk import pos_tag
from snorkel.labeling import LabelModel
from snorkel.labeling import PandasLFApplier

from src.preprocessor.codeSearch_preprocessor import languages, natural_languages, formal_languages
from src.preprocessor.so_to_pandas import SO_to_pandas
from src.snorkel.encoding import lang_decoding, uri_decoding, diff_decoding, email_decoding
from src.snorkel.weak_labellers import *
from src.tagger.data_utils import O, UNK

tag_decoders = {
    **{
        lang: tag_encoding_factory(lang)[1] for lang in [
            'go',
            'javascript',
            'php',
            'python',
            'ruby',
            'java',
        ]
    },
    **{
        'uri': lambda x: uri_decoding[x],
        'diff': lambda x: diff_decoding[x],
        'email': lambda x: email_decoding[x],
    }
}


def main(argv):
    location = argv[0]

    all_languages = languages + natural_languages + formal_languages

    # Define the set of labeling functions (LFs)
    lfs_lang = [
        frequency_language_factory(),
        lf_builtin_language,
        lf_uri_lang,
        lf_diff_lang,
        lf_email_lang,
    ]
    # Not all lf-s exist for all langs, we filter None to avoid issues.
    lfs_tags_per_lang = {**{lang: [x for x in [frequency_labeling_function_factory(lang),
                                               lf_builtin_tag_factory(lang)] if x is not None] for lang in languages},
                         **{
                             'uri': [lf_uri_tok],
                             'diff': [lf_diff_tok],
                             'email': [lf_email_tok],
                         }}
    size_lang_voc = len(all_languages)  # 6 (PL) + 1 (NL) + 3 (FL) = 10

    df_train = SO_to_pandas(location)

    # Apply the LFs to the unlabeled training data
    applier = PandasLFApplier(lfs_lang)
    L_lang_train = applier.apply(df_train)

    # Train the label model and compute the training labels
    lang_label_model = LabelModel(cardinality=size_lang_voc, verbose=True)
    lang_label_model.fit(L_lang_train, n_epochs=2000, log_freq=200, seed=42)
    df_train["lang_label"] = lang_label_model.predict(L=L_lang_train, tie_break_policy="abstain")

    for language in languages:
        tag_dict = Dictionary.load('./data/frequency_data/%s/tags.dct' % language)
        size_tag_voc = len(tag_dict)
        # Apply the LFs to the unlabeled training data
        tapplier = PandasLFApplier(lfs_tags_per_lang[language])
        L_train = tapplier.apply(df_train)

        # Train the label model and compute the training labels
        label_model = LabelModel(cardinality=size_tag_voc, verbose=True)
        label_model.fit(L_train, n_epochs=2000, log_freq=200, seed=42)
        df_train["label_%s" % language] = label_model.predict(L=L_train, tie_break_policy="abstain")

    max_post_id = df_train.iloc[-1]['PostIdx']
    valid_index = int(0.6 * max_post_id)
    test_index = int(0.8 * max_post_id)
    os.makedirs('./data/corpora/multilingual/so', exist_ok=True)
    for index, row in df_train.iterrows():
        if row['PostIdx'] > test_index:
            filename = 'valid.txt'
        elif row['PostIdx'] > valid_index:
            filename = 'dev.txt'
        else:
            filename = 'train.txt'

        # We use the NLTK pos_tag function for POS tags rather than snorkeling.
        eng_tag = UNK
        for tok, tag in pos_tag(row['Context']):
            if tok == row['Token']:
                eng_tag = tag
                break

        with open('./data/corpora/multilingual/so/%s' % filename, 'a') as f:
            to_output = [row['Token'], eng_tag] \
                        + [tag_decoders[language](row['label_%s' % language])
                           if row['label_%s' % language] != -1 else row['Language']
                           for language in languages + formal_languages] \
                        + [lang_decoding(row['lang_label']) if row['lang_label'] != -1 else 'English']
            f.write(' '.join(to_output) + '\n')


if __name__ == '__main__':
    main(sys.argv[1:])