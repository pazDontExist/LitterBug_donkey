#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jul  4 12:32:53 2017

@author: wroscoe
"""
import os
import sys
import time
import json
import datetime
import random
import glob
import numpy as np
import pandas as pd

from PIL import Image
from donkeycar import utils



class Tub(object):
    """
    A datastore to store sensor data in a key, value format.

    Accepts str, int, float, image_array, image, and array data types.

    For example:

    #Create a tub to store speed values.
    >>> path = '~/mydonkey/test_tub'
    >>> inputs = ['user/speed', 'cam/image']
    >>> types = ['float', 'image']
    >>> t=Tub(path=path, inputs=inputs, types=types)

    """

    def __init__(self, path, inputs=None, types=None):

        self.path = os.path.expanduser(path)
        print('path_in_tub:', self.path)
        self.meta_path = os.path.join(self.path, 'meta.json')
        self.df = None

        exists = os.path.exists(self.path)

        if exists:
            # load log and meta
            print("Tub exists: {}".format(self.path))
            with open(self.meta_path, 'r') as f:
                self.meta = json.load(f)
            self.current_ix = self.get_last_ix() + 1

        elif not exists and inputs:
            print('Tub does NOT exist. Creating new tub...')
            # create log and save meta
            os.makedirs(self.path)
            self.meta = {'inputs': inputs, 'types': types}
            with open(self.meta_path, 'w') as f:
                json.dump(self.meta, f)
            self.current_ix = 0
            print('New tub created at: {}'.format(self.path))
        else:
            msg = "The tub path you provided doesn't exist and you didnt pass any meta info (inputs & types)" + \
                  "to create a new tub. Please check your tub path or provide meta info to create a new tub."

            raise AttributeError(msg)

        self.start_time = time.time()

    def get_last_ix(self):
        index = self.get_index()
        return max(index)

    def update_df(self):
        df = pd.DataFrame([self.get_json_record(i) for i in self.get_index(shuffled=False)])
        self.df = df

    def get_df(self):
        if self.df is None:
            self.update_df()
        return self.df

    def get_index(self, shuffled=True):
        files = next(os.walk(self.path))[2]
        record_files = [f for f in files if f[:6]=='record']
        
        def get_file_ix(file_name):
            try:
                name = file_name.split('.')[0]
                num = int(name.split('_')[1])
            except:
                num = 0
            return num

        nums = [get_file_ix(f) for f in record_files]
        
        if shuffled:
            random.shuffle(nums)
        else:
            nums = sorted(nums)
            
        return nums 


    @property
    def inputs(self):
        return list(self.meta['inputs'])

    @property
    def types(self):
        return list(self.meta['types'])

    def get_input_type(self, key):
        input_types = dict(zip(self.inputs, self.types))
        return input_types.get(key)

    def write_json_record(self, json_data):
        path = self.get_json_record_path(self.current_ix)
        try:
            with open(path, 'w') as fp:
                json.dump(json_data, fp)
        except TypeError:
            print('troubles with record:', json_data)
        except FileNotFoundError:
            raise
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise

    def get_num_records(self):
        import glob
        files = glob.glob(os.path.join(self.path, 'record_*.json'))
        return len(files)

    def make_record_paths_absolute(self, record_dict):
        d = {}
        for k, v in record_dict.items():
            if type(v) == str: #filename
                if '.' in v:
                    v = os.path.join(self.path, v)
            d[k] = v

        return d

    def check(self, fix=False):
        """
        Iterate over all records and make sure we can load them.
        Optionally remove records that cause a problem.
        """
        print('Checking tub:%s.' % self.path)
        print('Found: %d records.' % self.get_num_records())
        problems = False
        for ix in self.get_index(shuffled=False):
            try:
                self.get_record(ix)
            except:
                problems = True
                if fix == False:
                    print('problems with record:', self.path, ix)
                else:
                    print('problems with record, removing:', self.path, ix)
                    self.remove_record(ix)
        if not problems:
            print("No problems found.")

    def remove_record(self, ix):
        """
        remove data associate with a record
        """
        record = self.get_json_record_path(ix)
        os.unlink(record)

    def put_record(self, data):
        """
        Save values like images that can't be saved in the csv log and
        return a record with references to the saved values that can
        be saved in a csv.
        """
        json_data = {}
        self.current_ix += 1
        
        for key, val in data.items():
            typ = self.get_input_type(key)

            if typ in ['str', 'float', 'int', 'boolean']:
                json_data[key] = val

            elif typ is 'image':
                path = self.make_file_path(key)
                val.save(path)
                json_data[key]=path

            elif typ == 'image_array':
                img = Image.fromarray(np.uint8(val))
                name = self.make_file_name(key, ext='.jpg')
                img.save(os.path.join(self.path, name))
                json_data[key]=name

            else:
                msg = 'Tub does not know what to do with this type {}'.format(typ)
                raise TypeError(msg)

        self.write_json_record(json_data)
        return self.current_ix

    def get_json_record_path(self, ix):
        return os.path.join(self.path, 'record_'+str(ix).zfill(6)+'.json')

    def get_json_record(self, ix):
        path = self.get_json_record_path(ix)
        try:
            with open(path, 'r') as fp:
                json_data = json.load(fp)
        except UnicodeDecodeError:
            raise Exception('bad record: %d. You may want to run `python manage.py check --fix`' % ix)
        except FileNotFoundError:
            raise
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise

        record_dict = self.make_record_paths_absolute(json_data)
        return record_dict

    def get_record(self, ix):

        json_data = self.get_json_record(ix)
        data = self.read_record(json_data)
        return data

    def read_record(self, record_dict):
        data={}
        for key, val in record_dict.items():
            typ = self.get_input_type(key)

            # load objects that were saved as separate files
            if typ == 'image_array':
                img = Image.open((val))
                val = np.array(img)

            data[key] = val
        return data

    def make_file_name(self, key, ext='.png'):
        name = '_'.join([str(self.current_ix).zfill(6), key, ext])
        name = name = name.replace('/', '-')
        return name

    def delete(self):
        """ Delete the folder and files for this tub. """
        import shutil
        shutil.rmtree(self.path)

    def shutdown(self):
        pass

    def get_record_gen(self, record_transform=None, shuffle=True, df=None):

        if df is None:
            df = self.get_df()

        while True:
            for row in self.df.iterrows():
                if shuffle:
                    record_dict = df.sample(n=1).to_dict(orient='record')[0]

                if record_transform:
                    record_dict = record_transform(record_dict)

                record_dict = self.read_record(record_dict)

                yield record_dict

    def get_batch_gen(self, keys, record_transform=None, batch_size=128, shuffle=True, df=None):

        record_gen = self.get_record_gen(record_transform, shuffle=shuffle, df=df)

        if keys is None:
            keys = list(self.df.columns)

        while True:
            record_list = []
            for _ in range(batch_size):
                record_list.append(next(record_gen))

            batch_arrays = {}
            for i, k in enumerate(keys):
                arr = np.array([r[k] for r in record_list])
                # if len(arr.shape) == 1:
                #    arr = arr.reshape(arr.shape + (1,))
                batch_arrays[k] = arr
            yield batch_arrays

    def get_train_gen(self, X_keys, Y_keys, batch_size=128, record_transform=None, df=None):

        batch_gen = self.get_batch_gen(X_keys + Y_keys,
                                       batch_size=batch_size,
                                       record_transform=record_transform,
                                       df=df)

        while True:
            batch = next(batch_gen)
            X = [batch[k] for k in X_keys]
            Y = [batch[k] for k in Y_keys]
            yield X, Y

    def get_train_val_gen(self, X_keys, Y_keys, batch_size=128, record_transform=None, train_frac=.8):
        train_df = self.df.sample(frac=train_frac, random_state=200)
        val_df = self.df.drop(train_df.index)

        train_gen = self.get_train_gen(X_keys=X_keys, Y_keys=Y_keys, batch_size=batch_size,
                                       record_transform=record_transform, df=train_df)

        val_gen = self.get_train_gen(X_keys=X_keys, Y_keys=Y_keys, batch_size=batch_size,
                                     record_transform=record_transform, df=val_df)

        return train_gen, val_gen

    def tar_records(self, file_path, start_ix, end_ix, ):
        """
        Create a tarfile of the records and metadata from a tub.

        :param start_ix:
        :param end_ix:
        :return:
        """

        for i in range(start_ix, end_ix):
            record_path = self.get_json_record_path(i)








class TubWriter(Tub):
    def __init__(self, *args, **kwargs):
        super(TubWriter, self).__init__(*args, **kwargs)

    def run(self, *args):
        """
        Accepts values, pairs them with their input keys and saves them
        to disk.
        """

        assert len(self.inputs) == len(args)
        record = dict(zip(self.inputs, args))
        self.put_record(record)


class TubReader(Tub):
    def __init__(self, path, *args, **kwargs):
        super(TubReader, self).__init__(*args, **kwargs)

    def run(self, *args):
        """
        Accepts keys to read from the tub and retrieves them sequentially.
        """

        record = self.get_record()
        record = [record[key] for key in args ]
        return record


class TubHandler():
    def __init__(self, path):
        self.path = os.path.expanduser(path)

    def get_tub_list(self,path):
        folders = next(os.walk(path))[1]
        return folders

    def next_tub_number(self, path):
        def get_tub_num(tub_name):
            try:
                num = int(tub_name.split('_')[1])
            except:
                num = 0
            return num

        folders = self.get_tub_list(path)
        numbers = [get_tub_num(x) for x in folders]
        # numbers = [i for i in numbers if i is not None]
        next_number = max(numbers+[0]) + 1
        return next_number

    def create_tub_path(self):
        tub_num = self.next_tub_number(self.path)
        date = datetime.datetime.now().strftime('%y-%m-%d')
        name = '_'.join(['tub', str(tub_num).zfill(2), date])
        tub_path = os.path.join(self.path, name)
        return tub_path

    def new_tub_writer(self, inputs, types):
        tub_path = self.create_tub_path()
        tw = TubWriter(path=tub_path, inputs=inputs, types=types)
        return tw



class TubImageStacker(Tub):
    '''
    A Tub for training a NN with images that are the last three records stacked 
    togther as 3 channels of a single image. The idea is to give a simple feedforward
    NN some chance of building a model based on motion.
    If you drive with the ImageFIFO part, then you don't need this.
    Just make sure your inference pass uses the ImageFIFO that the NN will now expect.
    '''
    
    def rgb2gray(self, rgb):
        '''
        take a numpy rgb image return a new single channel image converted to greyscale
        '''
        return np.dot(rgb[...,:3], [0.299, 0.587, 0.114])

    def stack3Images(self, img_a, img_b, img_c):
        '''
        convert 3 rgb images into grayscale and put them into the 3 channels of
        a single output image
        '''
        width, height, _ = img_a.shape

        gray_a = self.rgb2gray(img_a)
        gray_b = self.rgb2gray(img_b)
        gray_c = self.rgb2gray(img_c)
        
        img_arr = np.zeros([width, height, 3], dtype=np.dtype('B'))

        img_arr[...,0] = np.reshape(gray_a, (width, height))
        img_arr[...,1] = np.reshape(gray_b, (width, height))
        img_arr[...,2] = np.reshape(gray_c, (width, height))

        return img_arr

    def get_record(self, ix):
        '''
        get the current record and two previous.
        stack the 3 images into a single image.
        '''
        data = super(TubImageStacker, self).get_record(ix)

        if ix > 1:
            data_ch1 = super(TubImageStacker, self).get_record(ix - 1)
            data_ch0 = super(TubImageStacker, self).get_record(ix - 2)

            json_data = self.get_json_record(ix)
            for key, val in json_data.items():
                typ = self.get_input_type(key)

                #load objects that were saved as separate files
                if typ == 'image':
                    val = self.stack3Images(data_ch0[key], data_ch1[key], data[key])
                    data[key] = val
                elif typ == 'image_array':
                    img = self.stack3Images(data_ch0[key], data_ch1[key], data[key])
                    val = np.array(img)

        return data



class TubTimeStacker(TubImageStacker):
    '''
    A Tub for training N with records stacked through time. 
    The idea here is to force the network to learn to look ahead in time.
    Init with an array of time offsets from the current time.
    '''

    def __init__(self, frame_list, *args, **kwargs):
        '''
        frame_list of [0, 10] would stack the current and 10 frames from now records togther in a single record
        with just the current image returned.
        [5, 90, 200] would return 3 frames of records, ofset 5, 90, and 200 frames in the future.

        '''
        super(TubTimeStacker, self).__init__(*args, **kwargs)
        self.frame_list = frame_list
  
    def get_record(self, ix):
        '''
        stack the N records into a single record.
        Each key value has the record index with a suffix of _N where N is
        the frame offset into the data.
        '''
        data = {}
        for i, iOffset in enumerate(self.frame_list):
            iRec = ix + iOffset
            
            try:
                json_data = self.get_json_record(iRec)
            except FileNotFoundError:
                pass
            except:
                pass

            for key, val in json_data.items():
                typ = self.get_input_type(key)

                # load only the first image saved as separate files
                if typ == 'image' and i == 0:
                    val = Image.open(os.path.join(self.path, val))
                    data[key] = val                    
                elif typ == 'image_array' and i == 0:
                    d = super(TubTimeStacker, self).get_record(ix)
                    data[key] = d[key]
                else:
                    '''
                    we append a _offset to the key
                    so user/angle out now be user/angle_0
                    '''
                    new_key = key + "_" + str(iOffset)
                    data[new_key] = val
        return data


class TubGroup(Tub):
    def __init__(self, tub_paths_arg):
        tub_paths = utils.expand_path_arg(tub_paths_arg)
        print('TubGroup:tubpaths:', tub_paths)
        tubs = [Tub(path) for path in tub_paths]
        self.input_types = {}

        record_count = 0
        for t in tubs:
            t.update_df()
            record_count += len(t.df)
            self.input_types.update(dict(zip(t.inputs, t.types)))

        print('joining the tubs {} records together. This could take {} minutes.'.format(record_count,
                                                                                         int(record_count / 300000)))

        self.meta = {'inputs': list(self.input_types.keys()),
                     'types': list(self.input_types.values())}

        self.df = pd.concat([t.df for t in tubs], axis=0, join='inner')


import sqlite3


class SQLiteTub():
    def __init__(self, path, channel_schema, serializer):

        self.channel_schema = channel_schema
        self.channels = [c['name'] for c in channel_schema]
        self.types = [c['type'] for c in channel_schema]
        self.serializer = serializer

        self.record_cols = ['id', 'timestamp', 'active'] + self.channels

        self.db = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
        self.create_channel_table()
        self.create_records_table(channel_schema)

    def create_channel_table(self):
        sql = '''
          CREATE TABLE IF NOT EXISTS channel(
          id integer PRIMARY KEY,
          name text NOT NULL,
          type text 
          );
          '''
        self._insert(sql)

    def create_records_table(self, channel_schema):
        sql = "CREATE TABLE IF NOT EXISTS records( "
        col_lines = [
            'id INTEGER PRIMARY KEY AUTOINCREMENT',
            "timestamp TIMESTAMP DEFAULT(STRFTIME('%Y-%m-%d %H:%M:%f', 'NOW'))",
            'active INTEGER DEFAULT 1',
        ]
        for channel in channel_schema:
            line = "{} {}".format(
                channel['name'],
                self.serializer.sqlite_type(channel['type'])
            )
            col_lines.append(line)
        sql += ', '.join(col_lines) + ");"
        self._insert(sql)

    def put_record(self, *values):
        serialized_values = self.serializer.write_many(self.types, values)
        sql = '''
        INSERT INTO records{} values({}); 
        '''.format(
            tuple(self.channels),
            ','.join(['?'] * len(values))
        )
        self._insert(sql, serialized_values)

    def _select_records(self, cols='*', limit=10):

        if cols is not '*':
            cols = ','.join(cols)

        sql = '''
        SELECT {} FROM records 
        ORDER BY ID DESC
        LIMIT {};
        '''.format(cols, limit)

        recs = self._select(sql)

        new_records = []
        for r in recs:
            new_records.append(self.deserialize_record(r))
        return new_records

    def read_record(self, ix):
        """
        Return the deserialized record as a dictionary.
        """
        sql = 'SELECT * FROM records WHERE id = {};'.format(ix)
        record = self._select_one(sql)
        values = self.deserialize_record(record)
        record_dict = dict(zip(self.record_cols, values))
        return record_dict

    def deserialize_record(self, record):
        new_record = list(record[:3])
        new_record += self.serializer.read_many(stub.types, record[3:])
        return new_record

    def mark_previous_records_inactive(self, count=100):
        last_record = self.last_record_id()
        min_record = max(1, last_record - count)

        sql = '''
        UPDATE records
        SET active = 0
        WHERE ID <= {} AND ID > {};
        '''.format(last_record, min_record)
        self._insert(sql)

    def last_record_id(self):
        return self._select('SELECT last_insert_rowid()')[0][0]

    def _insert(self, sql, values=None):
        c = self.db.cursor()
        if values is not None:
            c.execute(sql, values)
        else:
            c.execute(sql)
        db.commit()

    def _select(self, sql):
        c = self.db.cursor()
        c.execute(sql)
        return c.fetchall()

    def _select_one(self, sql):
        c = self.db.cursor()
        c.execute(sql)
        return c.fetchone()

    def summary(self):
        data = {}
        data['records_columns'] = self._select('PRAGMA table_info(records);')
        data['records_total'] = self._select('SELECT COUNT(*) FROM records;')
        data['last_record_id'] = self.last_record_id()
        data['records_active'] = self._select('SELECT COUNT(*) FROM records WHERE active > 0;')
        return data

    def shutdown(self):
        self.db.close()

    def delete(self):
        """ Delete the db. """
        self.shutdown()

        import shutil
        shutil.rmtree(self.path)


import pickle


class TypeRegistry():
    def __init__(self):
        self.reg = {}
        self._load_defaults()

    def add(self, name,
            read_func=None, write_func=None,
            sqlite_type=None):

        entry = {}
        entry['read'] = read_func or (lambda x: x)
        entry['write'] = write_func or (lambda x: x)

        if self.is_sqlite_type(sqlite_type):
            entry['sqlite_type'] = sqlite_type

        self.reg[name] = entry

    def _load_defaults(self):
        self.add(int, sqlite_type='INTEGER')
        self.add(float, sqlite_type='REAL')
        self.add(str, sqlite_type='TEXT')
        self.add(list, read_func=pickle.loads, write_func=pickle.dumps, sqlite_type='BLOB')
        self.add(tuple, read_func=pickle.loads, write_func=pickle.dumps, sqlite_type='BLOB')
        self.add(dict, read_func=pickle.loads, write_func=pickle.dumps, sqlite_type='BLOB')
        self.add('blob', read_func=pickle.loads, write_func=pickle.dumps, sqlite_type='BLOB')

    @staticmethod
    def is_sqlite_type(value):
        sqlite_type_options = [
            'TEXT',
            'BLOB',
            'REAL',
            'INTEGER'
        ]
        if value is not None:
            return value.upper() in sqlite_type_options
        raise ValueError('Could not find sqlite_type for value {}'.format(value))

    def write(self, name, value):
        return self.reg[name]['write'](value)

    def read(self, name, value):
        return self.reg[name]['read'](value)

    def sqlite_type(self, name):
        return self.reg[name]['sqlite_type']

    def test_type(self, name, value):
        assert self.read(name, self.write(name, value)) == value
        return True

    def write_many(self, types, values):
        return tuple([self.write(t, v) for v, t in zip(values, types)])

    def read_many(self, type_names, serialized_values):
        return tuple([self.read(t, v) for v, t in zip(serialized_values, type_names)])