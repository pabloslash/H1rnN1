from pdb import set_trace as bp
import numpy as np
from Bio import SeqIO
import pandas as pd
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import OneHotEncoder
from helper import get_idx
from collections import Counter

'''
Class for handling fasta files. It essentially generates random combinations
of AA sequences from the specified years. Currently can only generate
AA sequences from a winter > summer > winter combination.
'''
class FastaSampler(object):
    def __init__(self, north_fasta, south_fasta,
                 start='$', end='%', delim0='&', delim1='@', pad_char='_'):
        self.start = start
        self.end = end
        self.delim0 = delim0
        self.delim1 = delim1
        self.pad_char = pad_char
        self.handle_files(north_fasta, south_fasta)
        self.train_years = None
        self.validation_years = None

    def handle_files(self, north_fasta, south_fasta):
        self.north, v1 = self.__parse_fasta_to_list(north_fasta)
        self.south, v2 = self.__parse_fasta_to_list(south_fasta)
        vocab_temp = ''.join(list(set(list(v1) + list(v2))))
        self.__generate_vocabulary(vocab_temp)

    def __generate_vocabulary(self, vocabulary):
        vocabulary += self.start
        vocabulary += self.end
        vocabulary += self.delim0
        vocabulary += self.delim1
        self.vocabulary = get_idx(vocabulary)
        # This is for the zero padding character.
        self.vocabulary[self.pad_char] = 0
        self.inverse_vocabulary = {v: k for k, v in self.vocabulary.items()}

    def __parse_fasta_to_list(self, some_fasta, specified_len=566):
        fasta_sequences = SeqIO.parse(open(some_fasta),'fasta')
        data = {}
        num_missing = 0
        num_too_long = 0
        seqs = set()
        # Basic data structure for our samples.

        for f in fasta_sequences:
            template = {
                        'id': '',
                        'year': '',
                        'month': '',
                        'day': '',
                        'location': '',
                        'seq': ''
                         }
            desc = f.description
            desc_split = desc.split(' ')

            date = desc_split[-2]
            date_split = date.split('/')
            year = int(date_split[0])
            try:
                month = int(date_split[1])
                day = int(date_split[2])
            except ValueError:
                num_missing += 1
                continue

            if len(f.seq) != specified_len:
                num_too_long += 1
                continue

            location = desc_split[1].split('/')[1]
            seq = str(f.seq)
            [seqs.add(s) for s in list(seq)]

            template['id'] = f.id
            template['year'] = year
            template['month'] = month
            template['day'] = day
            template['location'] = location
            template['seq'] = seq


            if year not in data.keys():
                data[year] = []

            data[year].append(template)
        print('Missing data: {}'.format(num_missing))
        print('Bad length data: {}'.format(num_too_long))
        # self.__generate_vocabulary(''.join(list(seqs)))
        return data, ''.join(list(seqs))

    def set_validation_years(self, validation):
        all_years = self.north.keys()
        self.train_years = list(set(all_years) - set(validation))
        self.validation_years = list(set(all_years) - set(self.train_years))

        # Get rid of first year because it actually can't be sampled From
        # Because there is no earlier year.
        self.train_years.sort()
        self.train_years = self.train_years[1:]
        self.validation_years.sort()
        self.validation_years = self.validation_years[:-1]

    def generate_N_random_samples_and_targets(self, N, group='train',
                                              slice_len=None):
        if self.train_years is None:
            raise ValueError('Please set train and validation years first')
        output = []

        while len(output) < N:
            num_samples = np.random.randint(N - len(output) + 1)
            if group.lower() == 'train':
                year = self.train_years[np.random.randint(len(self.train_years))]
            elif group.lower() == 'validation':
                year = self.validation_years[np.random.randint(len(self.validation_years))]
            output += self.generate_N_sample_per_year(num_samples, year)

        if slice_len is not None:
            targets = []
            for i, sample in enumerate(output):
                index = np.random.randint(max(1, len(sample) - slice_len))
                sliced = sample[index: index + slice_len]
                target = sample[index + 1: index + slice_len + 1]
                if len(sliced) < slice_len:
                    sliced += [self.vocabulary[self.pad_char]] * (slice_len - len(sliced))
                if len(target) < slice_len:
                    target += [self.vocabulary[self.pad_char]] * (slice_len - len(target))
                output[i] = sliced
                targets.append(target)

            return output, targets
        else:
            return output, output


    def __get_winter_sample(self, N, year, possibles, upper, lower):
        winter_seq = []
        while len(winter_seq) < N:
            ind = np.random.randint(len(possibles))
            sample = possibles[ind]
            if (sample['year'] == year and sample['month'] <= upper) or \
                    (sample['year'] == year - 1 and sample['month'] >= lower):
                winter_seq.append(sample['seq'])
        return winter_seq


    def __get_summer_sample(self, year, possibles, upper, lower):
        summer_seq = []
        while len(summer_seq) < N:
            ind = np.random.randint(len(possibles))
            sample = possibles[ind]
            if (sample['year'] == year and sample['month'] <= s_upper and \
                    sample['month'] >= s_lower):
                summer_seq.append(sample['seq'])
        return summer_seq

    # If you want samples from the 2012/2013 winter, 2013 summer, and 2014 winter,
    # supply 2013 as the year.
    def generate_N_sample_per_year(self,
                                   N,
                                   year,
                                   full=True,
                                   to_num=True,
                                   pattern=['W', 'S', 'W']
                                   ):
        if year not in self.north.keys() or year not in self.south.keys() or \
                year + 1 not in self.north.keys() or year - 1 not in self.north.keys():
            raise ValueError('Specified year ({}) is not present in dataset.\n' \
                             'Maximum year is: {}'.format(year, max(self.north.keys())))
        if len(pattern) > 3:
            raise ValueError('Please only supply patterns of length 3')
        # Months bounding the flu season. w = winter. and s = summer for
        # southern hemisphere.
        w_upper = 5
        w_lower = 10
        s_upper = 10
        s_lower = 5

        to_return = []
        all_seqs = []
        current_year = year
        for i, p in enumerate(pattern):
            if not i == 0 and not (p.lower() == 's' and pattern[i-1].lower() == 'w'):
                current_year += 1
            if p.lower() == 'w':
                possible_winters = self.north[current_year] + self.north[current_year - 1]
                exs = self.__get_winter_sample(N, current_year,
                                               possible_winters,
                                               w_upper, w_lower)
            elif p.lower() == 's':
                possible_summers = self.south[current_year]
                exs = self.__get_winter_sample(N, current_year,
                                               possible_summers,
                                               s_upper, s_lower)
            all_seqs.append(exs)

        # If we want the full sequence (for training) vs. if we only want
        # the first two portions (for priming for generation).
        if full:
            to_return = [self.start + all_seqs[0][i] + self.delim0 +
                         all_seqs[1][i] + self.delim1 + all_seqs[2][i] +
                         self.end for i in range(N)]
        else:
            to_return = [self.start + all_seqs[0][i] + self.delim0 +
                         all_seqs[1][i] + self.delim1 for i in range(N)]

        if to_num:
            to_return = [[self.vocabulary[c] for c in characters] for characters in to_return]

        return to_return


    '''
    Returns a dictionary where the keys are amino acids and the
    values are a list of the count of that amino acid at the given
    position across all samples. Way less useful than the funciton below.
    '''
    def get_AA_counts_by_position(self, year, north=True, plot=False):
        if north:
            data = self.north[year]
        else:
            data = self.south[year]

        AAs = set(''.join([d['seq'] for d in data]))
        to_return = {}
        for aa in AAs:
            to_return[aa] = [0] * len(data[0]['seq'])

        for i in range(len(data)):
            sample = data[i]
            for j in range(len(sample['seq'])):
                aa = sample['seq'][j]
                to_return[aa][j] += 1

        if plot:
            ind = np.arange(len(data[0]['seq']))
            width = 0.35
            prev = [0] * len(ind)
            for aa, counts in to_return.items():
                plt.bar(ind, counts, width, label=aa, bottom=prev)
                prev += counts
            plt.show()

        return to_return


    '''
    Get pandas dataframe with counts of each AA by position.
    '''
    def get_AA_counts_dataframe(self, year, north=True, plot=False):
        if north:
            data = self.north[year]
        else:
            data = self.south[year]

        alphabet = ''.join(list(set(''.join([s['seq'] for s in data]))))
        all_seq = [s['seq'] for s in data]
        char_to_int = dict((c, i) for i, c in enumerate(alphabet))
        integer_encoded = [[char_to_int[char] for char in d] for d in all_seq]

        AAs = list(set(''.join([d['seq'] for d in data])))
        to_return = np.zeros((len(data[0]['seq']), len(AAs)))

        for i in range(len(data)):
            sample = data[i]['seq']
            values = list(sample)
            if i == 0:
                label_encoder = LabelEncoder()
                label_encoder.fit(list(AAs))
                labs = label_encoder.classes_
                onehot_encoder = OneHotEncoder(sparse=False, n_values=len(AAs))
            integer_encoded = label_encoder.transform(values)
            integer_encoded = integer_encoded.reshape(len(integer_encoded), 1)
            if i == 0:
                onehot_encoded = onehot_encoder.fit(integer_encoded)
            onehot_encoded = onehot_encoder.transform(integer_encoded)
            to_return += onehot_encoded
        to_return = pd.DataFrame(to_return, index=np.arange(len(data[0]['seq'])), columns=labs)
        return to_return

    def get_freq_sequence(self, year, north=True, plot=False):
        if north:
            data = self.north[year]
        else:
            data = self.south[year]
        alphabet = ''.join(list(set(''.join([s['seq'] for s in data]))))
        all_seq = [s['seq'] for s in data]
        data = Counter(all_seq)
        seq_freq = data.most_common()
        max_freq = data.most_common(1)
        return seq_freq, max_freq
