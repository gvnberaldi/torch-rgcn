import rdflib as rdf
import pandas as pd
import gzip, os, wget, pickle, tqdm
from collections import Counter
from rdflib import URIRef

S = os.sep

def locate_file(filepath):
    directory = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    return directory + '/' + filepath

def st(node):
    """
    Maps an rdflib node to a unique string. We use str(node) for URIs (so they can be matched to the classes) and
    we use .n3() for everything else, so that different nodes don't become unified.

    Source: https://github.com/pbloem/gated-rgcn/blob/1bde7f28af8028f468349b2d760c17d5c908b58b/kgmodels/data.py#L16

    :param node:
    :return:
    """
    if type(node) == URIRef:
        return str(node)
    else:
        return node.n3()

def load_strings(file):
    """ Read triples file """
    with open(file, 'r') as f:
        return [line.split() for line in f]


# TODO: May be rewrite this without RDFlib dependency - Low priority
def load_node_classification_data(name, use_test_set=False, limit=None, disable_cache=True, val_prop=0.4):
    """
    Load knowledge graphs for node classification experiment.

    Source: https://github.com/pbloem/gated-rgcn/blob/1bde7f28af8028f468349b2d760c17d5c908b58b/kgmodels/data.py#L42

    :param name: Dataset name ('aifb', 'am', 'bgs' or 'mutag')
    :param use_test_set: If true, load the canonical test set, otherwise split a validation set off from the training data.
    :param limit: If set, the number of unique relations will be limited to this value, plus one for the self-connections,
                  plus one for the remaining connections combined into a single, new relation.
    :param disable_cache: If true, does not load from cache.
    :param val_prop: Size of the validation split from the training data (Default: 0.4).
    :return: A tuple containing the graph data, and the node classification test and train sets:
              - edges: dictionary of edges (relation -> pair of lists cont. subject and object indices respectively)
    """
    REST = '.rest'
    INV = 'inv.'

    # Check if the data has been cached for quick loading.
    cachefile = locate_file(f'data{S}{name}{S}cache_{"test" if use_test_set else "validation"}.pkl')
    if not disable_cache and os.path.isfile(cachefile) and limit is None:
        print('Using cached data...')
        with open(cachefile, 'rb') as file:
            data = pickle.load(file)
            print('Loaded.')
            return data
    print('Loading data from scratch...')

    if name.lower() == 'aifb':
        file = locate_file('data/aifb/aifb_stripped.nt.gz')
        train_file = locate_file('data/aifb/trainingSet.tsv')
        test_file = locate_file('data/aifb/testSet.tsv')
        label_header = 'label_affiliation'
        nodes_header = 'person'
    elif name.lower() == 'am':
        file = locate_file('data/am/am_stripped.nt.gz')
        train_file = locate_file('data/am/trainingSet.tsv')
        test_file = locate_file('data/am/testSet.tsv')
        label_header = 'label_cateogory'
        nodes_header = 'proxy'
    elif name.lower() == 'bgs':
        file = locate_file('data/bgs/bgs_stripped.nt.gz')
        train_file = locate_file('data/bgs/trainingSet(lith).tsv')
        test_file = locate_file('data/bgs/testSet(lith).tsv')
        label_header = 'label_lithogenesis'
        nodes_header = 'rock'
    elif name.lower() == 'mutag':
        file = locate_file('/data/mutag/mutag_stripped.nt.gz')
        train_file = locate_file('/data/mutag/trainingSet.tsv')
        test_file = locate_file('/data/mutag/testSet.tsv')
        label_header = 'label_mutagenic'
        nodes_header = 'bond'
    else:
        raise ValueError(f'Could not find \'{name}\' dataset')

    labels_train = pd.read_csv(train_file, sep='\t', encoding='utf8')
    if use_test_set:
        labels_test = pd.read_csv(test_file, sep='\t', encoding='utf8')
    else:
        # Split the training data into train and validation
        ltr = labels_train
        pivot = int(len(ltr) * val_prop)

        labels_test = ltr[:pivot]
        labels_train = ltr[pivot:]

    labels = labels_train[label_header].astype('category').cat.codes
    train = {}
    for nod, lab in zip(labels_train[nodes_header].values, labels):
        train[nod] = lab

    labels = labels_test[label_header].astype('category').cat.codes
    test = {}
    for nod, lab in zip(labels_test[nodes_header].values, labels):
        test[nod] = lab

    print('Labels loaded.')

    # Parse the data with RDFLib
    graph = rdf.Graph()

    if file.endswith('nt.gz'):
        with gzip.open(file, 'rb') as f:
            graph.parse(file=f, format='nt')
    else:
        graph.parse(file, format=rdf.util.guess_format(file))

    print('RDF loaded.')

    # Collect all node and relation labels
    triples = graph

    nodes = set()
    relations = Counter()

    for s, p, o in triples:
        nodes.add(st(s))
        nodes.add(st(o))

        relations[st(p)] += 1

    i2n = list(nodes) # maps indices to labels
    n2i = {n:i for i, n in enumerate(i2n)} # maps labels to indices

    # Truncate the list of relations if necessary
    if limit is not None:
        i2r = [r[0] for r in  relations.most_common(limit)] + [REST, INV+REST]
        # the 'limit' most frequent labels are maintained, the rest are combined into label REST to save memory
    else:
        i2r =list(relations.keys())

    r2i = {r: i for i, r in enumerate(i2r)}

    # TODO: Discard the code below
    # # Collect all edges into a dictionary: relation -> (from, to) (only storing integer indices)
    # edges = {}
    # for s, p, o in tqdm.tqdm(triples):
    #     s, p, o = n2i[st(s)], st(p), n2i[st(o)]
    #
    #     pf = r2i[p] if (p in r2i) else r2i[REST]
    #
    #     if pf not in edges:
    #         edges[pf] = [], []
    #
    #     edges[pf][0].append(s)
    #     edges[pf][1].append(o)

    # Collect all edges into a list: [from, relation, to] (only storing integer indices)
    edges = list()
    for s, p, o in tqdm.tqdm(triples):
        s, p, o = n2i[st(s)], st(p), n2i[st(o)]
        pf = r2i[p] if (p in r2i) else r2i[REST]
        edges.append([s, pf, o])

    print('Graph loaded.')

    # Cache the results for fast loading next time
    if limit is None:
        with open(cachefile, 'wb') as file:
            pickle.dump([edges, (n2i, i2n), (r2i, i2r), train, test], file)

    return edges, (n2i, i2n), (r2i, i2r), train, test

def load_link_prediction_data(name, use_test_set=False, limit=None):
    """
    Load knowledge graphs for link prediction experiment.

    Source: https://github.com/pbloem/gated-rgcn/blob/1bde7f28af8028f468349b2d760c17d5c908b58b/kgmodels/data.py#L218

    :param name: Dataset name ('aifb', 'am', 'bgs' or 'mutag')
    :param use_test_set: If true, load the canonical test set, otherwise load validation set from file.
    :param limit: If set, only the first n triples are used.
    :return: A tuple containing the graph data, and the link prediction test and train sets:
              - edges: dictionary of edges (relation -> pair of lists cont. subject and object indices respectively)
    """

    if name.lower() == 'fb15k':
        train_file = locate_file('data/fb15k/train.txt')
        val_file = locate_file('data/fb15k/valid.txt')
        test_file = locate_file('data/fb15k/test.txt')
    elif name.lower() == 'fb15k-237':
        train_file = locate_file('data/fB15k-237/train.txt')
        val_file = locate_file('data/fB15k-237/valid.txt')
        test_file = locate_file('data/fB15k-237/test.txt')
    elif name.lower() == 'wn18':
        train_file = locate_file('data/wn18/train.txt')
        val_file = locate_file('data/wn18/valid.txt')
        test_file = locate_file('data/wn18/test.txt')
    elif name.lower() == 'wn18rr':
        train_file = locate_file('data/wn18rr/train.txt')
        val_file = locate_file('data/wn18rr/valid.txt')
        test_file = locate_file('data/wn18rr/test.txt')
    else:
        raise ValueError(f'Could not find \'{name}\' dataset')

    train = load_strings(train_file)
    val = load_strings(val_file)
    test = load_strings(test_file)

    if not use_test_set:
        test = val
    else:
        train = train + val

    if limit:
        train = train[:limit]
        test = test[:limit]

    # Mappings for nodes (n) and relations (r)
    nodes, rels = set(), set()
    for triple in train + val + test:
        nodes.add(triple[0])
        rels.add(triple[1])
        nodes.add(triple[2])

    i2n, i2r = list(nodes), list(rels)
    n2i, r2i = {n: i for i, n in enumerate(nodes)}, {r: i for i, r in enumerate(rels)}

    # TODO: Discard the code below
    # # Collect train and test triples into two dictionaries: relation -> (from, to) (only storing integer indices)
    # train_triples = {i: ([], []) for i in r2i.values()}
    # test_triples = {i: ([], []) for i in r2i.values()}
    #
    # for s, p, o in train:
    #     s, p, o = n2i[s], r2i[p], n2i[o]
    #     train_triples[p][0].append(s)
    #     train_triples[p][1].append(o)
    #
    # for s, p, o in test:
    #     s, p, o = n2i[s], r2i[p], n2i[o]
    #     test_triples[p][0].append(s)
    #     test_triples[p][1].append(o)
    #
    # assert train_triples.keys() == test_triples.keys(), \
    #     "The order of relations in the test and train set must be the same!"

    train = [[n2i[st[0]], r2i[st[1]], n2i[st[2]]] for st in train]
    test = [[n2i[st[0]], r2i[st[1]], n2i[st[2]]] for st in test]

    return (n2i, i2n), (r2i, i2r), train, test
