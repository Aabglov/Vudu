###############################################################
#                        LBFGS THEANO
#                        No more fucking around
###############################################################

# THEANO
import numpy as np
import theano
import theano.tensor as T
from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams

# I/O
from numpy import genfromtxt
from matplotlib import pyplot as plot
import pickle
import os
import timeit
import sys
import zipfile
import random
import string
#from six.moves import range
from six.moves.urllib.request import urlretrieve

# SCIPY
import random
from math import e,log,sqrt
import scipy.optimize


# INIT RANDOM
srng = RandomStreams()
####################################################################################################
# CONSTANTS

# VARIABLES INIT
#X = T.matrix()
#y = T.matrix()
#X = T.ivector()
#Y = T.ivector()
max_len = T.iscalar('max_len')
X = T.iscalar('x')
Y = T.iscalar('y')
ACTUAL = T.ivector('actual')

vocab = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']

EOS = -1

MAX_WORD_SIZE = 10
# BATCHES
TRAIN_BATCHES = 1000
TEST_BATCHES = int(TRAIN_BATCHES)# * 0.2)
VALID_BATCHES = int(TRAIN_BATCHES * 0.2)
batch_size = 1#MAX_WORD_SIZE#20
embed_size = 256
num_nodes = 256
num_nodes2 = 256
num_nodes3 = 256
vocabulary_size = len(vocab)

n_epochs = 50000
cur_epoch = 0
cur_grad = 0.
use_saved = False

####################################################################################################

# I/O
def pickle_save(o,filename):
    with open(filename, 'wb') as f:
        pickle.dump(o,f)

def pickle_load(filename):
    with open(filename, 'rb') as f:
        o = pickle.load(f,encoding='latin1')
    return o

def thetaLoad(theta_val):
    return theano.shared(floatX(theta_val),name='theta',borrow=True)

def castData(data):
    return theano.shared(floatX(data),borrow=True)

def floatX(data):
    return np.asarray(data, dtype=theano.config.floatX)

def castInt(data):
    return np.asarray(data, dtype='int32')

def char2id(char):
  if char in vocab:
    return vocab.index(char)
  else:
    return 0
  
def id2char(dictid):
  if dictid != EOS:
    return vocab[dictid]
  else:
    return ' '

# Word helpers
def genRandWord():
  word_len = np.random.randint(1,MAX_WORD_SIZE)
  word = [id2char(np.random.randint(1,vocabulary_size)) for _ in range(word_len)]
  return ''.join(word)

def genRandBatch():
    word = genRandWord()
    batch = word2batch(word)
    rev_batch = word2batch(reverseWord(word))
    return castInt(batch),castInt(rev_batch)

# REVERSE HELPERS
def reverseWord(word):
  return word[::-1]

# BATCH CONVERSIONS
def batch2word(batch):
    return ''.join([id2char(i) for i in batch if i != EOS]) # Skip End of Sequence tag

def word2batch(word):
    batch = [char2id(letter) for letter in word] + [EOS] # Add End of Sequence tag
    return batch

def initFox():
    fox = []
    words = ['the','quick','brown','fox']
    for w in words:
        b = word2batch(w)
        r = word2batch(reverseWord(w))
        fox.append([b,castInt(r)])
    return fox

# RANDOM INIT
def init_weights(shape,name):
    return theano.shared(floatX(np.random.randn(*shape)*0.01),name=name,borrow=True)

# PROCESSING HELPERS
def rectify(X):
    return T.maximum(X,0.)

def dropout(X,p=0.):
    if p > 0:
        retain_prob = 1-p
        X *= srng.binomial(X.shape, p=retain_prob, dtype=theano.config.floatX)
        X /= retain_prob
    return X

# THETA PACKING/UNPACKING FOR LBFGS
def pack(weights):
    t = weights[0].ravel()
    for i in range(1,len(weights)):
        t = T.concatenate((t,weights[i].ravel())) 
    return t

def unpack(t,shapes):
    prev_ind = 0
    weights = {}
    for k,v in iter(shapes.items()):
        x = v['x']
        y = v['y']
        ind = x * y
        weights[k] =  t[prev_ind:prev_ind+ind].reshape((x,y))
        prev_ind += ind
    return weights

def thetaShape(shapes):
    total_size = 0
    for s in shapes:
        total_size += shapes[s]['x'] * shapes[s]['y']
    return (total_size,)

# MODEL AND OPTIMIZATION
######################################################################

def RMSprop(cost, params, lr=0.001, rho=0.9, epsilon=1e-6):
    grads = T.grad(cost=cost, wrt=params)
    updates = []
    for p, g in zip(params, grads):
        acc = theano.shared(p.get_value() * 0.)
        acc_new = rho * acc + (1 - rho) * g ** 2
        gradient_scaling = T.sqrt(acc_new + epsilon)
        g = g / gradient_scaling
        g = T.clip(g,-5.,5)
        updates.append((acc, acc_new))
        updates.append((p, p - lr * g))
    return updates

class RNN:
    def __init__(self,theta,shapes,states_packed,state_shapes,batch_size,vocabulary_size,embed_size):
        self.batch_size = batch_size
        self.vocabulary_size = vocabulary_size
        self.embed_size = embed_size
        weights = unpack(theta,shapes)
        states = unpack(states_packed,state_shapes)
        # The packing/unpacking process doesn't presever order
        # have to rearrange them here
        self.embed = weights['embed']
        self.x_all = weights['x_all']
        self.m_all= weights['m_all']
        self.ib = weights['ib']
        self.fb = weights['fb']
        self.cb = weights['cb']
        self.ob = weights['ob']
        # Hidden Cell
        self.h_x_all = weights['h_x_all']
        self.h_m_all = weights['h_m_all']
        self.h_ib = weights['h_ib']
        self.h_fb = weights['h_fb']
        self.h_cb = weights['h_cb']
        self.h_ob = weights['h_ob']
        # Hidden Cell 2
        self.h2_x_all = weights['h2_x_all']
        self.h2_m_all = weights['h2_m_all']
        self.h2_ib = weights['h2_ib']
        self.h2_fb = weights['h2_fb']
        self.h2_cb = weights['h2_cb']
        self.h2_ob = weights['h2_ob']
        # Hidden Cell 3
        self.h3_x_all = weights['h3_x_all']
        self.h3_m_all = weights['h3_m_all']
        self.h3_ib = weights['h3_ib']
        self.h3_fb = weights['h3_fb']
        self.h3_cb = weights['h3_cb']
        self.h3_ob = weights['h3_ob']
        # Final Weights
        self.w = weights['w']
        self.b = weights['b']

        # STATES
        self.ss = states['ss']
        self.so = states['so']
        self.hss = states['hss']
        self.hso = states['hso']
        self.h2ss = states['h2ss']
        self.h2so = states['h2so']
        self.h3ss = states['h3ss']
        self.h3so = states['h3so']

    # Definition of the cell computation.
    def lstm_cell(i,o,state,n,x_all,m_all,ib,fb,cb,ob):
        """Create a LSTM cell. See e.g.: http://arxiv.org/pdf/1402.1128v1.pdf
        Note that in this formulation, we omit the various connections between the
        previous state and the gates."""
        i_mul = T.dot(i,x_all)
        o_mul = T.dot(o,m_all)

        ix_mul = i_mul[:,:n]# tf.matmul(i, ix)
        fx_mul = i_mul[:,n:2*n]# tf.matmul(i, fx)
        cx_mul = i_mul[:,2*n:3*n]# tf.matmul(i, cx)
        ox_mul = i_mul[:,3*n:]# tf.matmul(i, ox)

        im_mul = o_mul[:,:n] # tf.matmul(o,im)
        fm_mul = o_mul[:,n:2*n] # tf.matmul(o,fm)
        cm_mul = o_mul[:,2*n:3*n] # tf.matmul(o,cm)
        om_mul = o_mul[:,3*n:] # tf.matmul(o,om)

        input_gate = T.nnet.sigmoid(ix_mul + im_mul + ib)
        forget_gate = T.nnet.sigmoid(fx_mul + fm_mul + fb)
        update = cx_mul + cm_mul + cb
        state = (forget_gate * state) + (input_gate * T.tanh(update))
        output_gate = T.nnet.sigmoid(ox_mul + om_mul + ob)
        return output_gate * T.tanh(state), state

    def forward_prop(self,X):
        #MODEL
        e = self.embed[X].reshape((self.batch_size,self.embed_size))
        self.so,self.ss     = lstm_cell(e,    so,   ss,   num_nodes,  x_all,    m_all,    ib,    fb,    cb,    ob)
        hso,hss   = lstm_cell(so,   hso,  hss,  num_nodes2, h_x_all,  h_m_all,  h_ib,  h_fb,  h_cb,  h_ob)
        h2so,h2ss = lstm_cell(hso,  h2so, h2ss, num_nodes3, h2_x_all, h2_m_all, h2_ib, h2_fb, h2_cb, h2_ob)
        h3so,h3ss = lstm_cell(h2so, h3so, h3ss, vocabulary_size, h3_x_all, h3_m_all, h3_ib, h3_fb, h3_cb, h3_ob)
        pyx = T.nnet.softmax(T.dot(h3so,w) + b)
        pred = T.argmax(pyx,axis=1)

        # Repackage saved states
        state_list = [ss,so,hss,hso,h2ss,h2so,h3ss,h3so]
        states_packed = pack(state_list)
        
        return pred,pyx,states_packed
        

# SHAPES OF WEIGHT MATRICES
shapes = {'embed':{'x':vocabulary_size+1,'y':embed_size}, # Note we have one extra row for the EOS tag (index -1)
              'x_all':{'x':embed_size,'y':4*num_nodes},
              'm_all':{'x':num_nodes,'y':4*num_nodes},
              'ib':{'x':1,'y':num_nodes},
              'fb':{'x':1,'y':num_nodes},
              'cb':{'x':1,'y':num_nodes},
              'ob':{'x':1,'y':num_nodes},
              
              # NOT TRAINED
              #'saved_output':{'x':batch_size,'y':num_nodes},
              #'saved_state':{'x':batch_size,'y':num_nodes},
              
              # Hidden Cell
              'h_x_all':{'x':num_nodes,'y':4*num_nodes2},

              'h_m_all':{'x':num_nodes2,'y':4*num_nodes2},
              'h_ib':{'x':1,'y':num_nodes2},
              'h_fb':{'x':1,'y':num_nodes2},
              'h_cb':{'x':1,'y':num_nodes2},
              'h_ob':{'x':1,'y':num_nodes2},

              # NOT TRAINED
              #'h_saved_output':{'x':batch_size,'y':num_nodes2},
              #'h_saved_state':{'x':batch_size,'y':num_nodes2},

               # Hidden Cell 2
              'h2_x_all':{'x':num_nodes2,'y':4*num_nodes3},
              'h2_m_all':{'x':num_nodes3,'y':4*num_nodes3},
              'h2_ib':{'x':1,'y':num_nodes3},
              'h2_fb':{'x':1,'y':num_nodes3},
              'h2_cb':{'x':1,'y':num_nodes3},
              'h2_ob':{'x':1,'y':num_nodes3},

              # NOT TRAINED
              #'h2_saved_output':{'x':batch_size,'y':num_nodes2},
              #'h2_saved_state':{'x':batch_size,'y':num_nodes2},

               # Hidden Cell 3
              'h3_x_all':{'x':num_nodes3,'y':4*vocabulary_size},
              'h3_m_all':{'x':vocabulary_size,'y':4*vocabulary_size},
              'h3_ib':{'x':1,'y':vocabulary_size},
              'h3_fb':{'x':1,'y':vocabulary_size},
              'h3_cb':{'x':1,'y':vocabulary_size},
              'h3_ob':{'x':1,'y':vocabulary_size},

              # NOT TRAINED
              #'h3_saved_output':{'x':batch_size,'y':vocabulary_size},
              #'h3_saved_state':{'x':batch_size,'y':vocabulary_size},
              
              'w':{'x':vocabulary_size,'y':vocabulary_size},
              'b':{'x':1,'y':vocabulary_size},
              }

state_shapes = {'ss':{'x':batch_size,'y':num_nodes},
              'so':{'x':batch_size,'y':num_nodes},
                # Hidden states - layer 1
              'hss':{'x':batch_size,'y':num_nodes2},
              'hso':{'x':batch_size,'y':num_nodes2},
                # Hidden states - layer 2
              'h2ss':{'x':batch_size,'y':num_nodes3},
              'h2so':{'x':batch_size,'y':num_nodes3},
                 # Hidden states - layer 3
              'h3ss':{'x':batch_size,'y':vocabulary_size},
              'h3so':{'x':batch_size,'y':vocabulary_size}
            }


fox = initFox()

# initialize theta 
ts = thetaShape(shapes)
ss = thetaShape(state_shapes)

if use_saved:
    theta = castData(pickle_load('theta_orig.pkl'))
    states = castData(pickle_load('states_orig.pkl'))
else:
    theta = init_weights(ts,'theta')#thetaLoad(pickle_load('theta_orig.pkl'))
    states = init_weights(ss,'states')

y_pred,py,states = model(X,theta,shapes,states,state_shapes)

train = theano.function(inputs=[X], outputs=states, allow_input_downcast=True)

predict = theano.function(inputs=[X], outputs=y_pred, allow_input_downcast=True)

preds,updates = theano.scan(fn=lambda prior_result, X: predict(prior_result),
                              outputs_info=T.ones_like(X),
                              non_sequences=X,
                              n_steps=max_len)

cost = T.mean((preds - ACTUAL) ** 2)
params = [theta,states]
update = RMSprop(cost,params,lr=0.01)

learn = theano.function(inputs=[X,ACTUAL], outputs=cost, updates=update, allow_input_downcast=True)

start_time = timeit.default_timer()
print('Optimizing using RMSProp...')

for i in range(10000):

    c = 0.
    for _ in range(TRAIN_BATCHES):
        train_input,actual = genRandBatch()
        for j in range(len(new_batch[0])):
            # Train 1 letter at a time
            train(train_input[j])
        pred = predict(EOS)
        c += learn(EOS,actual)
    c /= TRAIN_BATCHES
    
    fox_pred = ''
    for _ in range(4):
        for f in fox[_][0]:
            fox_pred += id2char(predict(f)[0])
        fox_pred += ' '
    print('Completed iteration ',i,', Cost: ',c,'Fox Validation:',fox_pred)#'Input:',str_input,'True:',str_true,
    
    if not i % 100:
        ss,so,hss,hso,h2ss,h2so,h3ss,h3so = get_states(0)
        print('saved_output',so[:,0])
        pickle_save(theta.eval(),'theta.pkl')
        s = packStates(ss,so,hss,hso,h2ss,h2so,h3ss,h3so)
        pickle_save(s,'states.pkl')


end_time = timeit.default_timer()
print('The code ran for %.1fs' % ((end_time - start_time)))



