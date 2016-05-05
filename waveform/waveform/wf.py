import math
#from .cwaveform import *
import numpy
import matplotlib.pyplot as plt

    
def makeArrayToSend(b0, F_Burst_Time, Sampling_Freq, Burst_Width, Measuring_Time, Length, NCyc, Angle, Cell_Type):
	 
    b0_field_strength = b0 # muT

    gamma_xe = 11.77717 # (10^6 rad*s^-1*T^-1)/(2Pi)=MHz/T
    gamma_he = 32.4341  # 
    
    volt_per_muT = 17.29                                 ###volt_per_muT = 2*17.29 # V_pp / muT (Rafael)
    
    he_freq = gamma_he*b0_field_strength #[Hz]
    xe_freq = gamma_xe*b0_field_strength 

        
    f_burst_time = F_Burst_Time
    sampling_freq = Sampling_Freq
    
    my_arr = None
    i = 0
    list_of_wfs = []
    burst_width=Burst_Width  ###sig = Sig # s
    total_volts = 0
    measuring_time = Measuring_Time
    length=Length
    
    
    ncyc = NCyc
    angle = Angle
    angle = math.pi*2.*angle/360
    
    
    # Choose cell type (He/Xe/HeXe)
    cell_type = Cell_Type
                                                                        
    if cell_type == 1:
        cell = [(he_freq, gamma_he)]
    elif cell_type == 2:
        cell = [(xe_freq, gamma_xe)]
    elif cell_type == 3:
        cell = [(he_freq, gamma_he), (xe_freq, gamma_xe)]
        
    for f, gam in cell:     ###for f, gam in [(he_freq, gamma_he), (xe_freq, gamma_xe)]:
        n = int(f*f_burst_time)
        aphase = math.pi/2 - (f*f_burst_time - n)*2*math.pi 
        assert( aphase < 2*math.pi )
        an_arr = make_array(burst_width=burst_width, measuring_time=measuring_time, 
                            first_burst_time = f_burst_time, sampling_freq = sampling_freq, 
                            burst_freq=f, phase=aphase, length=length, ncyc=ncyc)        ###an_arr = make_array(burst_width=sig, measuring_time=measuring_time, first_burst_time = f_burst_time, sampling_freq = sampling_freq, burst_freq=f, phase=aphase, length=length, ncyc=ncyc)
        
 
       
        amp=(1./(gam*2*math.pi))*angle/(math.sqrt(2*math.pi)*burst_width/(2.35482))#sigma=burst_width/(2*sqrt(2*ln(2)))                          ###amp = (1./gam)/(2*math.sqrt(2*math.pi)*sig) # (muT)
        # Theta = B_1 * Tau * g
        
        
        amp *= volt_per_muT*2                  # Factor 2: B_x = 2* B_1
        if my_arr is not None:
            my_arr += amp*an_arr
        else:
            my_arr = amp*an_arr
                                                                                            ###total_volts += amp 
    if max(my_arr) > (-min(my_arr)):
        total_volts_vpp = max(my_arr)*2
    else:
        total_volts_vpp = -min(my_arr)*2                           
    my_arr /= total_volts_vpp/2                                           ###my_arr /= total_volts
    
    
    
    X=range(len(my_arr))
    plt.plot(X, my_arr)
    plt.show()

    
    
    
    return [my_arr, total_volts_vpp]                               ###return [my_arr,total_volts]
    #return an_arr
    
def start():
    #b0, F_Burst_Time,Sampling_Freq, Burst_Width, Measuring_Time, Length, NCyc, Angle, He/Xe/HeXe (1, 2, 3)
	 return start_params(1.2, 2.0, 1000, 0.3, 2, 72600, 36, 20, 1)
	

def trigger():
    print("Sending Trigger signal to device")
    so = AgilentWaveform("waveform.1.nedm1", 5025)
    so.cmd_and_return("*TRG")
    print("Waveform triggered")
	
def startWithData(my_arr, total_volts_vpp, sampling_Freq = "100 kHz"):    ###def startWithData(my_arr, total_volts, sampling_Freq = "100 kHz"):
    print("Send WF to device")
    
   
    #### Abbruch da eine Verbinding nicht möglich ist (M)
    ###return                                                    ####
    so = AgilentWaveform("waveform.1.nedm1", 5025)
    
    print("Sending")
    so.send_wf(my_arr, "temp2", sampling_Freq, "%s Vpp" % str(total_volts_vpp), "0 V")   ###so.send_wf(my_arr, "temp2", sampling_Freq, "%s Vpp" % str(total_volts), "0 V")
    setup_cmds = [
      ("*IDN?", None),# ID
      ("SYST:COMM:LAN:MAC?", None),# ID
      ("BURS:NCYC 1", None),# ID
      ("BURSt:MODE TRIG", None),# ID
      ("TRIG:SOUR BUS", None),# ID
      ("BURSt:STATe 1", None),# ID
      ("OUTP 1", None),# ID
    ]
    for c, f in setup_cmds:
        ret = so.cmd_and_return(c)
        print c, ret 
        if f:
            if f(ret): print "Pass"
            else: 
                print "Fail"
        so.check_errors()
        so.cmd_and_return("*WAI")

    print("Connection closed")
    #so.close()
    return my_arr
	
	
def start_params(b0, F_Burst_Time, Sampling_Freq, Burst_Width, Measuring_Time, Length, NCyc, Angle, Cell_Type):  ###def start_params(b0, F_Burst_Time, Sampling_Freq, Sig, Measuring_Time, Length, NCyc, Angle): 
    print b0, F_Burst_Time,Sampling_Freq, Burst_Width, Measuring_Time, Length, NCyc, Angle, Cell_Type    ###print b0, F_Burst_Time,Sampling_Freq, Sig, Measuring_Time, Length, NCyc, Angle
    arr = makeArrayToSend(b0, F_Burst_Time, Sampling_Freq, Burst_Width, Measuring_Time, Length, NCyc, Angle, Cell_Type)   ###arr = makeArrayToSend(b0, F_Burst_Time, Sampling_Freq, Sig, Measuring_Time, Length, NCyc, Angle)
    my_arr = arr[0]
    total_volts_vpp = arr[1]                                    ###total_volts = arr[1]
    
    samplingFreq = "{} kHz".format(int(Sampling_Freq) / 1000)
    startWithData(my_arr, total_volts_vpp, samplingFreq)                  ###startWithData(my_arr, total_volts, samplingFreq)
    
    
    #raw_input("E")
    #########################
    # DRAWING THE PLOT
    #########################
    #import ROOT
    #dbl = ROOT.TDoubleWaveform(total_volts*my_arr, len(my_arr))
    #dbl.SetSamplingFreq(1e-4) # 100 kHz
    #wfft = ROOT.TWaveformFT()
    #ROOT.TFastFourierTransformFFTW.GetFFT(len(dbl)).PerformFFT(dbl, wfft)
    #c1 = ROOT.TCanvas()
    #ahist = wfft.GimmeHist()
    #ahist.GetXaxis().SetRangeUser(0, 2*he_freq*1e-6)
    #ahist.Draw()
    #c1.Update()
    #plt.plot(my_arr)
    #plt.show()
    #dbl.GimmeHist().Draw()
    #c = 1
    #for h in list_of_wfs:
    #    ah = h.GimmeHist(str(c))
    #    ah.SetLineColor(c)
    #    ah.Draw('same')
    #    c+= 1
    #c1.Update()   
    #raw_input("E")
    
    
if __name__ == "__main__":
	start()
