# -*- coding: utf-8 -*-
"""
Created by Tangui Aladjidi on the 28/05/2020
"""

import numpy as np
import matplotlib.pyplot as plt
from time import time
from mpl_toolkits.axes_grid1 import make_axes_locatable
import time
import cupy as cp
from scipy.ndimage import zoom
from WISH_lkb import WISH_Sensor
from PIL import Image
from SLM import SLMscreen
import slmpy
import cv2
import EasyPySpin
from scipy import ndimage

# plt.switch_backend("QT5Agg")

# WISH routine


def alignment(frame):
    """
    Detects the center of a frame provided the beam is circular
    :param frame: Input frame
    :return: T the translation matrix to correct the image using OpenCV
    """
    # frame_blurred = cv2.blur(frame, (12, 12))
    ret1, thresh = cv2.threshold(frame, 70, 255, 0)
    thresh_blurred = cv2.blur(thresh, (12, 12))
    M = cv2.moments(thresh_blurred)
    cX = int(M["m10"] / M["m00"])
    cY = int(M["m01"] / M["m00"])
    T = np.float32([[1, 0, int(frame.shape[1]/2) - cX],
                    [0, 1, int(frame.shape[0]/2) - cY]])
    return T


def main():
    # start timer
    T0 = time.time()
    # instantiate WISH sensor reading the conf file
    Sensor = WISH_Sensor("wish_3.conf")
    # load SLM flatness correction
    # corr = Image.open("/home/tangui/Documents/SLM/deformation_correction_pattern/CAL_LSH0802200_780nm.bmp")
    # corr = Image.open("/home/tangui/Documents/phase_retrieval/dev/phases/U14-2048-201133-06-04-07_808nm.png")
    corr = np.zeros((1080, 1920))
    wvl = Sensor.wavelength
    z3 = Sensor.z
    delta4x = Sensor.d_CAM
    delta4y = Sensor.d_CAM
    slm_type = 'SLM'
    # Setting up the camera for acquisition
    Cam = EasyPySpin.VideoCapture(0)
    zoom_factor = 1
    Nx = int(Cam.get(cv2.CAP_PROP_FRAME_WIDTH)*zoom_factor)
    Ny = int(Cam.get(cv2.CAP_PROP_FRAME_HEIGHT)*zoom_factor)
    delta3x = wvl * z3 / (Nx * delta4x)
    delta3y = wvl * z3 / (Ny * delta4y)
    ims = np.zeros((Ny, Nx, Sensor.Nim))
    if slm_type == 'DMD':
        resX, resY = 1920, 1080
        slm = np.ones((resY, resX, Sensor.N_mod))
        # slm_display = SLMscreen(resX, resY)
        slm_display = slmpy.SLMdisplay(isImageLock=True)

        slm_display.update(slm[:, :, 0])
        print(f"Displaying 1 st SLM pattern")
        for obs in range(Sensor.N_os):
            ret, frame = Cam.read()
            T = alignment(frame)
            frame = cv2.warpAffine(frame, T, frame.shape)
            ims[:, :, obs] = zoom(cv2.flip(frame, 0), zoom_factor)
        for i in range(1, int(Sensor.N_mod/2)):
            slm[:, :, 2 * i] = Sensor.modulate_binary((resY, resX), pxsize=1)
            slm_display.update(slm[:, :, 2 * i])
            for obs in range(Sensor.N_os):
                ret, frame = Cam.read()
                frame = alignment(frame)
                ims[:, :, 2 * Sensor.N_os*i+obs] = zoom(cv2.flip(frame, 0),
                                                        zoom_factor)
            slm[:, :, 2 * i + 1] = np.ones((resY, resX)) - slm[:, :, 2 * i]
            slm_display.update(slm[:, :, 2 * i+1])
            for obs in range(Sensor.N_os):
                ret, frame = Cam.read()
                frame = alignment(frame)
                ims[:, :, 2 * i + 1 + obs] = zoom(cv2.flip(frame, 0),
                                                  zoom_factor)
    elif slm_type == 'SLM':
        resX, resY = 1920, 1080
        angle = 0  # to correct for misalignment btwn camera and SLM
        slm_display = SLMscreen(resX, resY)
        # slm_display = slmpy.SLMdisplay(isImageLock=True)
        slm = np.ones((resY, resX, Sensor.N_mod))
        # slm_display.updateArray(slm[:, :, 0].astype('uint8'))
        slm_display.update(slm[:, :, 0].astype('uint8'))
        ret, frame = Cam.read()
        frame = cv2.flip(frame, 0)
        mask = frame > Sensor.threshold*np.max(frame)
        for i in range(0, Sensor.N_mod):
            slm[:, :, i] = Sensor.modulate((resY, resX), pxsize=8)
            # slm[:, :, i] = Sensor.modulate_binary((resY, resX), pxsize=10)
            print(f"Displaying {i + 1} th SLM pattern")
            # slm_display.updateArray((250*((1/255)*(256*slm[:, :, i]-corr)%256)).astype('uint8'))
            slm_display.update((250*((1/255)*(256*slm[:, :, i]-corr)%256)).astype('uint8'))
            slm_display.update((250*((1/255)*(256*slm[:, :, i]-corr)%256)).astype('uint8'))
            # time.sleep(1)
            for obs in range(Sensor.N_os):
                # time.sleep(0.05)
                ret, frame = Cam.read()
                # frame = cv2.warpAffine(frame, T, frame.shape)
                frame = cv2.flip(frame, 0)
                # frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                # frame = ndimage.rotate(frame, -angle, reshape=False)
                # ims[:,:,Sensor.N_os*i+obs]= zoom(frame, zoom_factor)
                print(f"Recording image nbr : {Sensor.N_os*i+obs}")
                ims[:, :, Sensor.N_os*i+obs] = frame*mask
        slm_display.close()
        Cam.release()
    if slm_type == 'DMD':
        SLM = Sensor.process_SLM(slm, Nx, Ny, delta4x, delta4y, type="amp")
        SLM[np.abs(SLM) > 0.5] = 1 + 1j*0
        SLM[SLM <= 0.5] = 0 + 1j*0
    elif slm_type == 'SLM':
        SLM = Sensor.process_SLM(slm, Nx, Ny, delta4x, delta4y, type="phi")

    print('\nModulated images are captured')
    # reconstruction
    # process the captured image : converting to amplitude and padding if needed
    ims = (ims/(2**8)).astype(np.float32)
    print('\nDisplaying captured images')
    y0 = Sensor.process_ims(ims, Nx, Ny)
    # for k in range(y0.shape[2]):
    plt.imshow(y0[:, :, 0], vmin=0, vmax=1)
    #    plt.imshow(y0[:,:,k], vmin=0, vmax=1)
    #    plt.title(f"{k}")
    #    plt.scatter(N/2,N/2, color='r', marker='.')
    plt.show()
    # Recon initilization
    T_run_0 = time.time()
    u3_est, u4_est, idx_converge = Sensor.WISHrun_vec(y0, SLM, delta3x,
                                                      delta3y, delta4x,
                                                      delta4y)
    np.save("u4_est.npy", u4_est)
    T_run = time.time()-T_run_0
    # Backpropagation distance for the 2nd plot
    z2 = 160e-3
    # u2_est = Sensor.frt_gpu(u4_est, Sensor.d_CAM, Sensor.d_CAM,
    #                         Sensor.wavelength, -z2)
    Z2 = np.linspace(95e-3, 400e-3, 25)
    for z2 in Z2:
        u2_est = Sensor.frt_gpu(u4_est, Sensor.d_CAM, Sensor.d_CAM,
                                Sensor.wavelength, -z2)
        u2_est = cp.asnumpy(u2_est)
        plt.imshow(np.abs(u2_est))
        plt.title(f"{1e3*z2} mm")
        plt.show()
    u2_est = cp.asnumpy(u2_est)
    u3_est = cp.asnumpy(u3_est)
    u4_est = cp.asnumpy(u4_est)
    # total time
    T = time.time()-T0
    print(f"\n Time spent in the GS loop : {T_run} s")
    print(f"\n Total time elapsed : {T} s")
    fig = plt.figure()
    ax3 = fig.add_subplot(141)
    ax4 = fig.add_subplot(142)
    ax6 = fig.add_subplot(143)
    ax5 = fig.add_subplot(144)
    divider3 = make_axes_locatable(ax3)
    cax3 = divider3.append_axes('right', size='5%', pad=0.05)
    divider4 = make_axes_locatable(ax4)
    cax4 = divider4.append_axes('right', size='5%', pad=0.05)
    divider6 = make_axes_locatable(ax6)
    cax6 = divider6.append_axes('right', size='5%', pad=0.05)
    im3 = ax3.imshow(abs(u4_est)**2, cmap='viridis', vmin=0, vmax=1)
    ax3.set_title('intensity estimation (camera plane)')
    im4 = ax4.imshow(np.angle(u4_est), cmap='twilight_shifted', vmin=-np.pi,
                     vmax=np.pi)
    ax4.set_title('Phase estimation')
    im6 = ax6.imshow(np.abs(u3_est)**2, cmap='viridis', vmin=0, vmax=1)
    ax6.set_title('Back-propagated field (SLM plane)')
    ax5.plot(5*np.arange(0, len(idx_converge), 1), idx_converge)
    ax5.set_title("Convergence curve")
    ax5.set_xlabel("Iteration")
    ax5.set_ylabel("RMS error of the estimated field")
    ax5.set_yscale('log')
    fig.colorbar(im3, cax=cax3)
    fig.colorbar(im4, cax=cax4)
    fig.colorbar(im6, cax=cax6)
    plt.show()
    fig = plt.figure()
    ax0 = fig.add_subplot(121)
    ax1 = fig.add_subplot(122)
    divider0 = make_axes_locatable(ax0)
    divider1 = make_axes_locatable(ax1)
    cax0 = divider0.append_axes('right', size='5%', pad=0.05)
    cax1 = divider1.append_axes('right', size='5%', pad=0.05)
    im0 = ax0.imshow(abs(u2_est) ** 2, cmap='viridis')  # , vmin=0, vmax=1)
    im1 = ax1.imshow(np.angle(u2_est), cmap='twilight_shifted', vmin=-np.pi,
                     vmax=np.pi)
    ax0.set_title("Back-propagated intensity")
    ax1.set_title("Back-propagated phase")
    fig.colorbar(im0, cax0)
    fig.colorbar(im1, cax1)
    plt.show()


if __name__ == "__main__":
    main()
