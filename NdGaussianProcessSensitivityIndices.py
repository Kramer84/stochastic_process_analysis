import openturns 
import numpy 
import matplotlib.pyplot as plt
from   joblib    import Parallel, delayed, cpu_count
from   itertools import chain


'''Here we are going to rewrite a vectorized method to calculate the Sobol' Indices,
using the different methods at our disposal : 
-Jansen
-Saltelli
-Mauntz-Kucherenko
-Martinez
This rewriting is necessary, as the version in openTURNS only allow samples
in the form of a matrix having a size of N(2+d) rows. (With d being the dimension
of the function analysed.) In the case of function governed by stochastic processes
the size of the samlpes will allways be smaller than N(2+d), as we work whith the KL
decomposition, and that in that case, the increase of the dimension of the function is 
due to the fact that for one field (one dimension) we express it using multiple simple RVs,
but that we only need to calculate one sensitity per field. 
We will write a basic function that takes as an input the sample A, B as well as the mixed matrix,
(And also the output vector associated to each of these samples) and solely calculates one 
sensitivity index. This will allow us to scale the method to any type of input sample size.
'''


class NdGaussianProcessSensitivityIndicesBase(object):
    '''Basic methods to calculate unitary sensitivity indices
    We first set the samples Y_A and Y_B and calculate the means and
    variances of those, so they don't have to be calculated again. 
    The notations are those of A. DUMAS in the paper :
    "Lois asymptotiques des estimateurs des indices de Sobol"


    This class can accept vectors (unidimensional outputs) as well
    as matrices (multidimensional outputs)

    The agregated Sobol indices are not calculated yet 
    '''
    @staticmethod
    def centerSobolExp(SobolExperiment, N):
        nSamps = int(SobolExperiment.shape[0]/N)
        inputListParallel = list()
        SobolExperiment0 = SobolExperiment
        dim = 1
        psi_fo, psi_to = NdGaussianProcessSensitivityIndicesBase.SymbolicSaltelliIndices(1)
        for i in range(nSamps):
            #Centering
            SobolExperiment[i*N:(i+1)*N,...] = SobolExperiment[i*N:(i+1)*N,...] - SobolExperiment[i*N:(i+1)*N,...].mean(axis=0)
        for p in range(nSamps-2):
            inputListParallel.append((SobolExperiment[:N,...], SobolExperiment[N:2*N,...], SobolExperiment[(2+p)*N:(3+p)*N,...], psi_fo, psi_to))
        return SobolExperiment, inputListParallel

    @staticmethod
    def getSobolIndices(SobolExperiment, N, method = 'Saltelli'):
        expShape = SobolExperiment.shape 
        nIndices = int(expShape[0]/N) - 2
        dim = expShape[1:]
        SobolExperiment0 = SobolExperiment
        if dim == (): dim = 1
        print('There are',nIndices,'indices to get in',dim,'dimensions with',SobolExperiment[0].size,'elements')
        SobolExperiment, inputListParallel = NdGaussianProcessSensitivityIndicesBase.centerSobolExp(SobolExperiment, N)
        if method is 'Saltelli':
            '''SobolIndices = Parallel(
                                                                        n_jobs = cpu_count())(
                                                                        delayed(NdGaussianProcessSensitivityIndicesBase.SaltelliIndices)(
                                                                        *inputListParallel[i]) for i in range(nIndices)
                                                                        )'''
            SobolIndices       = [NdGaussianProcessSensitivityIndicesBase.SaltelliIndices(*inputListParallel[i]) for i in range(nIndices)]
            SobolIndices, SobolIndicesTot, VarSobolIndices, VarSobolIndicesTot = map(list,zip(*SobolIndices))
            print('Indices successfully calculated')
            SobolIndices       = numpy.stack(SobolIndices)
            SobolIndicesTot    = numpy.stack(SobolIndicesTot)
            VarSobolIndices    = numpy.stack(VarSobolIndices)
            VarSobolIndicesTot = numpy.stack(VarSobolIndicesTot)
        return SobolIndices, SobolIndicesTot, VarSobolIndices ,VarSobolIndicesTot
        
    @staticmethod
    def SaltelliIndices(Y_Ac, Y_Bc, Y_Ec, psi_fo, psi_to):
        assert (Y_Ac.shape == Y_Bc.shape == Y_Ec.shape ), "samples have to have same shape"
        N = Y_Ac.shape[0]
        Ni = 1./N
        #Original version
        '''S = numpy.divide(numpy.substract(Ni*numpy.sum(numpy.multiply(Y_Bc,Y_Ec),axis=0),
                                                                 numpy.multiply(Ni*numpy.sum(Y_Bc,axis=0),
                                                                                Ni*numpy.sum(Y_Ac,axis=0))),
                                                 numpy.substract(Ni*numpy.sum(numpy.square(Y_Ac),axis=0),
                                                                 numpy.square(Ni*numpy.sum(Y_Ac,axis=0)))
                                                 )'''
        #Simplified indice as samples centered
        S = numpy.divide(Ni*numpy.sum(numpy.multiply(Y_Bc,Y_Ec),axis=0),
                                                     Ni*numpy.sum(numpy.square(Y_Ac),axis=0)
                                                     )
        S_tot = numpy.subtract(1., 
                    numpy.divide(Ni*numpy.sum(numpy.multiply(Y_Ac,Y_Ec),axis=0),
                                                     Ni*numpy.sum(numpy.square(Y_Ac)))
                                                     )
        varS, varS_tot = NdGaussianProcessSensitivityIndicesBase.computeVariance(Y_Ac, Y_Bc, Y_Ec, N, psi_fo, psi_to)
        return S, S_tot, varS, varS_tot

    @staticmethod
    def SymbolicSaltelliIndices(N):
        x, y = (openturns.Description.BuildDefault(N, 'X'), 
                       openturns.Description.BuildDefault(N, 'Y'))
        # in order X0, Y0, X1, Y1
        xy = list(x)
        for i, yy in enumerate(y):
            xy.insert(2*i+1, yy)
        # psi  = (x1 + x2 + ...) / (y1 + y2 + ...). 
        symbolic_num, symbolic_denom   = '',''

        symbolic_num,symbolic_denom  = ([item for sublist in zip(x,['+']*N) for item in sublist], 
                                               [item for sublist in zip(y,['+']*N) for item in sublist])
        (symbolic_num.pop(), symbolic_denom.pop())
        symbolic_num   = ''.join(symbolic_num)
        symbolic_denom   = ''.join(symbolic_denom)
        psi_fo, psi_to = (openturns.SymbolicFunction(xy, ['('+symbolic_num + ')/(' + symbolic_denom + ')']), 
                                 openturns.SymbolicFunction(xy, ['1 - ' + '('+symbolic_num + ')/(' + symbolic_denom + ')']))
        return psi_fo, psi_to

    @staticmethod
    def computeVariance(YAc, YBc, YEc, N, psi_fo, psi_to):
        """
        Compute the variance of the estimator sample

        Parameters
        ----------
        outputDim : int
            Dimension of the output (1 if scalar), only flat arrays
        N : int
            The size of the sample.
        outputDesign : numpy.array
            The array containing the output of the model for the whole simulation
        psi_fo : symbolic function
            First order saltelli indices symbolic function
        psi_to : symbolic function
            Total order saltelli indices symbolic function
        """
        baseShape = YAc.shape
        print('basic output shape is:', baseShape)
        flatDim   = int(numpy.prod(baseShape[1:]))
        flatShape = [N, flatDim]
        print('dimension of output flattened to matrix (dim<=2) ',flatDim)
        YAc = numpy.reshape(YAc, flatShape)
        YBc = numpy.reshape(YBc, flatShape)
        YEc = numpy.reshape(YEc, flatShape)

        #some intermediary calculus
        #first order:
        X_fo = numpy.multiply(YBc,YEc)
        Y_fo = numpy.square(YAc)

        #total order
        X_to = numpy.multiply(YAc,YEc)
        Y_to = numpy.square(YAc)  

        print('data for variance calculus prepared \n X_fo shape is', X_fo.shape, 'Y_fo shape is', Y_fo.shape)
        varianceFO = NdGaussianProcessSensitivityIndicesBase.computeSobolVariance(X_fo, Y_fo, psi_fo, N)
        varianceTO = NdGaussianProcessSensitivityIndicesBase.computeSobolVariance(X_to, Y_to, psi_to, N)
        shape      = baseShape[1:]
        if len(baseShape)<=1 : shape=(1,)
        varianceFO = numpy.reshape(varianceFO,shape)
        varianceTO = numpy.reshape(varianceTO,shape)
        return varianceFO, varianceTO


    @staticmethod
    def computeSobolVariance(X, Y, psi, N):
        """
        Compute the variance of the estimators (NON agregated)

        Parameters
        ---------- 
        U : sample
            The sample of yA, yB, yE or combination of them, defined according the
            sobol estimators
        psi : Function
            The function that computes the sobol estimates.
        N : int
            The size of the sample.
        """

        dims       = numpy.prod(X.shape[1:])  #1 if output has only one dimension, as numpy.prod(())=1
        covariance = numpy.squeeze(numpy.stack([numpy.cov((X[...,i],Y[...,i]),rowvar=True) for i in range(dims)]))
        print('The output has', dims, 'dimensions, so the covariance is of dimension',covariance.shape)
        if dims > 1:
            mean_samp      = numpy.stack(numpy.asarray(list(zip(X.mean(axis=0),Y.mean(axis=0)))).T).transpose()
            print('The shape of the means is:', mean_samp.shape)
            mean_samp_list = mean_samp.tolist()
            mean_psi       = numpy.stack([numpy.squeeze(numpy.asarray(psi.gradient(mean_samp_list[i])) )for i in range(len(mean_samp_list))])
            print('The shape of the mean value for psi is: ', mean_psi.shape)
            mean_psi_temp = numpy.stack([mean_psi.T, mean_psi.T]).T.transpose((0,2,1))
            print('temporary shape after tiling', mean_psi_temp.shape)
            P2            = numpy.sum(numpy.multiply(mean_psi_temp, covariance), axis = 1)  ## This line is similar to a dot product
            variance      = numpy.divide(numpy.sum(numpy.multiply(mean_psi,P2),axis=1),N)
            print('Variance is:', variance)

        else : 
            print('Covariance is:', covariance)
            mean_samp = numpy.array([X.mean(), Y.mean()]).tolist()
            print('Sample mean is:', mean_samp)
            meanPsi   = numpy.squeeze(psi.gradient(mean_samp))
            print('Psi mean is:', meanPsi)
            variance  = numpy.dot(meanPsi,numpy.dot(covariance, meanPsi))
            variance = variance/N
            print('variance is:', variance)
        return variance


class SobolIndicesClass(object):
    def __init__(self, SobolExperiment, N ,method = 'Saltelli'):
        self.method            = method
        self.N                 = N
        self.experiment        = SobolExperiment
        self.firstOrderIndices = None

    def getFirstOrderIndices(self):
        self.firstOrderIndices = NdGaussianProcessSensitivityIndicesBase.getSobolIndices(self.experiment, self.N, self,method)








def plotSobolIndicesWithErr(S, errS, varNames, n_dims):
    assert len(varNames)==n_dims,"Error in the number of dimensions or variable names"