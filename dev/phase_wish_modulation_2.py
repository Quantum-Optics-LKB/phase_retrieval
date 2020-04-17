# -*- coding: utf-8 -*-
"""
@author : Tangui ALADJIDI
"""
import numpy as np
import matplotlib.pyplot as plt
from LightPipes import *
from PIL import Image  # for custom phase / intensity masks
from time import time
from scipy.ndimage import interpolation
from mpl_toolkits.axes_grid1 import make_axes_locatable
import time
import sys
import configparser
import ast
from scipy import signal, interpolate

class WavefrontSensor:
    def __init__(self, cfg_path):
        conf = configparser.ConfigParser()
        conf.read(cfg_path)
        self.size_SLM = float(conf["params"]["size_SLM"])  # size of the SLM window
        self.size = float(conf["params"]["size"])  # size of the SLM window
        self.wavelength = float(conf["params"]["wavelength"])
        self.z = float(conf["params"]["z"])  # propagation distance
        self.N_gs = int(conf["params"]["N_gs"])  # number of GS iterations
        self.N_mod = int(conf["params"]["N_mod"])  # number of modulation steps
        self.mod_intensity = float(conf["params"]["mod_intensity"])  # modulation intensity
        self.SLM_levels = int(conf["params"]["SLM_levels"])  # number of SLM levels
        self.threshold = float(conf['params']['mask_threshold'])  # intensity threshold for the signal region
        self.elements = []  # list of optical elements
        for element in conf["setup"]:
            self.elements.append(ast.literal_eval(conf['setup'][element]))

    # progress bar
    def update_progress(self, progress):
        barLength = 20  # Modify this to change the length of the progress bar
        status = ""
        if isinstance(progress, int):
            progress = float(progress)
        if not isinstance(progress, float):
            progress = 0
            status = "error: progress var must be float\r\n"
        if progress < 0:
            progress = 0
            status = "Halt...\r\n"
        if progress >= 1:
            progress = 1
            status = "Done...\r\n"
        block = int(round(barLength * progress))
        text = "\rProgress : [{0}] {1}% {2}".format("#" * block + "-" * (barLength - block),
                                                    round(progress * 100, ndigits=1), status)
        sys.stdout.write(text)
        sys.stdout.flush()


    def define_mask(self, I: np.ndarray, plot: bool):
        """
        A function to define the signal region automatically from the provided intensity and threshold
        :param I: intensity from which to define a signal region
        :param threshold: intensities below threshold are discarded
        :param plot: Plot or not the defined mask
        :return: mask_sr the defined mask
        """
        threshold = self.threshold
        h, w = I.shape
        # compute FT
        I_tf = np.fft.fft2(I)
        I_tf = np.abs(np.fft.fftshift(I_tf))
        freq = np.fft.fftfreq(h, d= self.size / h)
        mask_sr = np.zeros((h, w))
        # detect outermost non zero target intensity point
        non_zero = np.array(np.where(I > self.threshold))
        non_zero_offset = np.zeros(non_zero.shape)
        # offset relative to center
        non_zero_offset[0] = non_zero[0] - (h / 2) * np.ones(len(non_zero[0]))
        non_zero_offset[1] = non_zero[1] - (w / 2) * np.ones(len(non_zero[1]))
        # Determine radii of each non-zero point
        R_non_zero = np.sqrt(non_zero_offset[0] ** 2 + non_zero_offset[1] ** 2)
        R_max = np.where(R_non_zero == np.max(abs(R_non_zero)))[0][
            0]
        # if there are several equally far points, it takes the
        # first one
        i_max, j_max = int(h / 2 + int(abs(non_zero_offset[0][R_max]))), int(
            w / 2 + int(abs(non_zero_offset[1][R_max])))
        i_min, j_min = int(h / 2 - int(abs(non_zero_offset[0][R_max]))), int(
            w / 2 - int(abs(non_zero_offset[1][R_max])))
        delta_i = int(i_max - i_min)
        delta_j = int(j_max - j_min)
        if delta_i > delta_j:
            mask_sr[i_min:i_max, i_min:i_max] = 1
        else:
            mask_sr[j_min:j_max, j_min:j_max] = 1
        if plot:
            fig = plt.figure(0)
            ax1 = fig.add_subplot(131)
            ax2 = fig.add_subplot(132)
            ax3 = fig.add_subplot(133)
            divider1 = make_axes_locatable(ax1)
            divider2 = make_axes_locatable(ax2)
            divider3 = make_axes_locatable(ax3)
            cax1 = divider1.append_axes('right', size='5%', pad=0.05)
            cax2 = divider2.append_axes('right', size='5%', pad=0.05)
            cax3 = divider3.append_axes('right', size='5%', pad=0.05)
            im1=ax1.imshow(I, cmap="viridis")
            ax1.set_title("Intensity")
            im2=ax2.imshow(mask_sr, cmap="viridis")
            ax2.set_title(f"Signal region (Threshold = {threshold})")
            scat = ax2.scatter(non_zero[0][R_max], non_zero[1][R_max], color='r')
            scat.set_label('Threshold point')
            ax2.legend()
            extent = [min(freq), max(freq), min(freq), max(freq)]
            im3 = ax3.imshow(I_tf, cmap="viridis", extent=extent)
            ax3.set_title("Fourier transform")
            fig.colorbar(im1, cax=cax1)
            fig.colorbar(im2, cax=cax2)
            fig.colorbar(im3, cax=cax3)
            plt.show()
        return mask_sr
    def propagate(self, I0: np.ndarray, phi0: np.ndarray, z: float):
        """
        Implements propagation using Fresnel diffraction
        :param I0: Intensity to propagate
        :param phi0: Phase of the field
        :param z : Propagation distance in metre
        :return: I, phi : Propagated field
        """
        wv = self.wavelength
        size = self.size
        size_SLM = self.size_SLM
        k=2*np.pi/wv
        #k=1/wv
        A0 = np.sqrt(I0)*np.exp(1j*phi0)
        x = np.linspace(0, I0.shape[0], I0.shape[0])-(I0.shape[0]/2)*np.ones(I0.shape[0])
        y = np.linspace(0, I0.shape[1], I0.shape[1])-(I0.shape[1]/2)*np.ones(I0.shape[1])
        x, y = x / np.max(x), y / np.max(y)
        X, Y = np.meshgrid(x,y)
        R = self.size*np.sqrt(X**2 + Y**2)
        D = np.exp(1j*k*z)/(1j*wv*z)
        Q = np.exp(1j*(k/(2*z))*R**2)
        A = D*Q*np.fft.fftshift(np.fft.fft2(A0*Q, norm='ortho'))
        #A = signal.fftconvolve(A0, D*Q, mode='full')
        #x1 = np.linspace(0, A.shape[0], A.shape[0])-(A.shape[0]/2)*np.ones(A.shape[0])
        #y1 = np.linspace(0, A.shape[1], A.shape[1])-(A.shape[1]/2)*np.ones(A.shape[1])
        #x1, y1 = x1 / np.max(x1), y1 / np.max(y1)
        I = np.abs(A)**2
        phi = np.angle(A)
        #interp_I = interpolate.RectBivariateSpline(x1, y1, I)
        #interp_phi = interpolate.RectBivariateSpline(x1, y1, phi)
        #I = interp_I(x, y)
        #phi = interp_phi(x, y)
        return I, phi

    def phase_retrieval_wish(self, I0: np.ndarray, I: list, Phi0: list, unwrap: bool = False, plot: bool = True, **kwargs):
        """
        Assumes the propagation in the provided setup to retrieve the phase from the intensity at the image plane
        :param I0: Source intensity field
        :param I: Intensity sample fields from which to retrieve the phase
        :param Phi0 : Phase masks
        :param k: Number of iterations for GS algorithm
        :param unwrap : Phase unwrapping at the end
        :param plot : toggle plots
        :param threshold : Threshold for automatic mask float in [0,1] default is 1e-2
        :param **mask_sr : Signal region  np.ndarray
        :param **phi0 : Initial phase of the source np.ndarray
        :return phi: The calculated phase map using Gerchberg-Saxton algorithm
        """
        k=self.N_gs
        threshold=self.threshold
        z=self.z
        size = self.size
        size_SLM = self.size_SLM
        wavelength = self.wavelength
        h_0, w_0 = I0.shape
        h, w = I[0].shape
        # initiate initial phase
        if "phi0" in kwargs:
            phi0 = kwargs["phi0"]
        else:
            phi0 = np.zeros((h, w))
        # if no masks are specified, the function defines one
        if "mask_sr" not in kwargs:
            mask_sr = self.define_mask(I[0], plot)
        elif kwargs["mask_sr"] == 'adaptative':
            mask_sr = np.ones((h, w))
        else:
            mask_sr = kwargs["mask_sr"]
        mask_nr = np.ones(mask_sr.shape) - mask_sr
        T0 = time.time()
        Signal_s=[]
        Signal_f=[]
        Phi=[]
        # initiate fields in the SLM plane
        for phi0 in Phi0:
            signal_s = Begin(size, wavelength, h)
            signal_s = SubIntensity(I0, signal_s)
            signal_s = SubPhase(phi0, signal_s)
            Signal_s.append(signal_s)
            Signal_f.append(0)
            Phi.append(phi0)
        phi = np.mean(np.array(Phi), axis=0)
        for i in range(k):
            T1 = time.time()
            #initialize the phase to the mean of the phases of the samples
            for k_s in range(len(Signal_s)):
                #submit new phase (mean phase+modulation)
                signal_s = SubPhase(phi+Phi[k_s], Signal_s[k_s])
                #signal_s = SubPhase(phi, signal_s)
                signal_f = Forvard(z, signal_s)  # Propagate to the far field
                # interpolate to target size
                signal_f = Interpol(size, h, 0, 0, 0, 1, signal_f)
                I_f_old = np.reshape(Intensity(0, signal_f), (h, w))  # retrieve far field intensity
                # if adaptative mask option, update the mask
                if "mask_sr" in kwargs and kwargs["mask_sr"] == 'adaptative':
                    mask_sr = self.define_mask(mask_sr * I_f_old, False)  # no plots
                signal_f = SubIntensity(I[k_s] * mask_sr + I_f_old * mask_nr,
                                        signal_f)  # Substitute the measured far field into the field only in the signal region
                Signal_f[k_s]=signal_f
            for k_f in range(len(Signal_f)):
                signal_s = Forvard(-z, Signal_f[k_f])  # Propagate back to the near field
                # interpolate to source size
                signal_s = Interpol(size, h_0, 0, 0, 0, 1, signal_s)
                signal_s = SubIntensity(I0, signal_s)  # Substitute the measured near field into the field
                pm_s = np.reshape(Phase(signal_s), I0.shape)
                Signal_s[k_f]=signal_s
                Phi[k_f]=-pm_s+Phi0[k_f]
            phi = np.mean(np.array(Phi), axis=0)
            T2 = time.time() - T1
            progress = float((i + 1) / k)
            self.update_progress(progress)


        if unwrap:
            phi = PhaseUnwrap(phi)
        phi = np.reshape(phi, (h, w))
        T3 = time.time() - T0
        print(f"Elapsed time : {T3} s")
        return phi, mask_sr


    # modulation
    def modulate(self, phi: np.ndarray):
        """
        A function to randomly modulating a phase map without introducing too much high frequency noise
        :param phi: Phase map to be modulated
        :param x : Modulation intensity. Must be between 0 and 1.
        :return: phi_m a modulated phase map to multiply to phi
        """
        x=self.mod_intensity
        # generate (N/10)x(N/10) random matrices that will then be upscaled through interpolation
        h, w = int(phi.shape[0] / 10), int(phi.shape[1] / 10)
        M = np.pi * (x * (np.ones((h, w)) - 2 * np.random.rand(h, w, )))  # random matrix between [-x*pi and x*pi]
        phi_m = interpolation.zoom(M, phi.shape[0] / h)
        phi_m = phi_m * np.pi  # bring phase between [-pi.pi]
        return phi_m


    def gaussian_profile(self, I: np.ndarray, sigma: float):
        """

        :param I: Intensity to which a gaussian profile is going to be applied
        :param sigma: Standard deviation of the gaussian profile, in fraction of the provided intensity size
        :return: I_gauss : the "gaussianized" intensity
        """
        h, w = I.shape
        # define a radial position matrix
        R = np.zeros((h, w))
        for i in range(h):
            for j in range(w):
                R[i, j] = np.sqrt((h / 2 - i) ** 2 + (w / 2 - j) ** 2)
        sig = sigma * max(h, w)
        G = np.exp(-R ** 2 / (2 * sig ** 2))
        I_gauss = I * G
        return I_gauss


Sensor=WavefrontSensor('wish.conf')
# initiate custom phase and intensity filters emulating the SLM
I0 = np.asarray(Image.open("intensities/I0_512_big.bmp"))[:, :, 0]  # extract only the first channel
phi0 = np.asarray(Image.open("phases/calib_512_big.bmp"))
I0 = Sensor.gaussian_profile(I0, 0.5) / np.max(I0)
phi0 = phi0 / np.max(phi0)
# signal region for the phase
phi0_sr = np.ones(phi0.shape)  # signal region
phi0_sr[np.where(I0 == 0)[0], np.where(I0 == 0)[1]] = 0
phi0_sr[np.where(I0 > 0)[0], np.where(I0 > 0)[1]] = 1
# conversion to rad
phi0 = 2 * np.pi * (phi0 - 0.5 * np.ones(phi0.shape)) * phi0_sr
Phi0 = []
Phi = []
I_target = []
for k in range(Sensor.N_mod):
    #for k in range(int(N_mod/2)):
    phi_m = phi0 + Sensor.modulate(phi0)
    Phi0.append(phi_m)
    #Phi0.append(-phi_m)
    #Phi0 = np.array(Phi0)
for phi_0 in Phi0:
    # define target field
    A = Begin(Sensor.size_SLM, Sensor.wavelength, I0.shape[0])
    A = SubIntensity(I0, A)
    A = SubPhase(phi_0, A)
    #A = Forvard(Sensor.z, A)
    #I = np.reshape(Intensity(1, A), I0.shape)
    I, phi = Sensor.propagate(I0, phi_0, Sensor.z)
    plt.imshow(I)
    plt.show()
    I_target.append(I)
I_target = np.array(I_target)
I = np.mean(I_target, axis=0)
phi, mask = Sensor.phase_retrieval_wish(I0, I_target, Phi0, plot=True)
# compute RMS
RMS = (1 / 2 * np.pi) * np.mean(np.sqrt(phi0_sr * (phi0 - phi) ** 2))
fig = plt.figure()
ax1 = fig.add_subplot(221)
ax2 = fig.add_subplot(222)
ax3 = fig.add_subplot(223)
ax4 = fig.add_subplot(224)
divider1 = make_axes_locatable(ax1)
cax1 = divider1.append_axes('right', size='5%', pad=0.05)
divider2 = make_axes_locatable(ax2)
cax2 = divider2.append_axes('right', size='5%', pad=0.05)
divider3 = make_axes_locatable(ax3)
cax3 = divider3.append_axes('right', size='5%', pad=0.05)
divider4 = make_axes_locatable(ax4)
cax4 = divider4.append_axes('right', size='5%', pad=0.05)
im1 = ax1.imshow(I0, vmin=0, vmax=1)
im2 = ax2.imshow(phi0, vmin=-np.pi, vmax=np.pi)
im3 = ax3.imshow(I, vmin=0, vmax=1)
im4 = ax4.imshow(phi, vmin=-np.pi, vmax=np.pi)
ax1.set_title("Initial intensity")
ax2.set_title("Initial phase")
ax3.set_title("Mean propagated intensity")
ax4.set_title("Mean retrieved phase")
ax4.text(8, 18, f"RMS = {round(RMS, ndigits=3)}", bbox={'facecolor': 'white', 'pad': 3})
fig.colorbar(im1, cax=cax1)
fig.colorbar(im2, cax=cax2)
fig.colorbar(im3, cax=cax3)
fig.colorbar(im4, cax=cax4)
plt.show()
