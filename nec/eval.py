# Copyright 2010 Nikolay Mladenov, Distributed under 
# GNU General Public License

import necmath,sys
from demathutils import v3add, v3mul, v3sub, v3dot, v3cross, v3len, v3unit, v3rotx, v3roty, v3rotz

output = "output"
input = "input.nec"
autosegmentation=10
ncores=4


class FrequencyData:
	def __init__(self, char_imp):
		self.freq = 0
		self.real = 0
		self.imag = 0
		self.gain = 0
		self.char_imp = char_imp
		self.angle = 0
	def swr(self):
		rc = necmath.sqrt( \
			(necmath.pow(self.real-self.char_imp,2)+necmath.pow(self.imag,2)) \
			/ (necmath.pow(self.real+self.char_imp,2)+necmath.pow(self.imag,2)) \
			)
		return (1+rc)/(1-rc)
	def valid(self):
		try: 
			self.swr()
			return 1
		except:
			return 0
	def net(self):
		tmp = 4*max(self.real,.0001)*self.char_imp/(necmath.pow(self.real+self.char_imp,2)+necmath.pow(self.imag,2))
		return self.gain+10*necmath.log10(tmp)
		
	def __str__(self):
		return "%d Mhz - raw(%f), net(%f), swr(%f), real(%f), imag(%f)"%(int(self.freq), self.gain, self.net(), self.swr(), self.real, self.imag)


class NecOutputParser:
	def __init__(self, output, agt=1, char_imp = 300, angle_step = 5, frequency_angle_data={}):
		self.frequencies = []
		self.char_imp = char_imp
		self.frequency_angle_data=frequency_angle_data
		self.angle_step = angle_step
		self.agt = 10*necmath.log10(agt)
		if output:
			self.parse(output)

	def printFreqs(self, header=1):
		if not self.frequency_angle_data:
			if header: 
				print "%6s %7s %7s %7s %7s %7s"%("Freq", "RawGain", "NetGain", "SWR", "Real", "Imag")
				print "================================================"
			if self.agt!=0:
				print "AGT=%g dB"%self.agt
			for i in self.frequencies:
				if not i.valid():
					print "%6.4g - invalid result"%i.freq
				else:
					print "%6.4g % 7.5g % 7.5g %7.5g %7.5g % 7.5g"%(int(i.freq), i.gain, i.net(),i.swr(), i.real, i.imag)
		else:
			if header: 
				print "%6s %7s %6s %7s %7s %7s %7s %7s %7s"%("Freq", "Target", "Angle", "RawGain", "NetGain", "SWR", "Real", "Imag", "Diff")
				print "======================================================"
			for i in self.frequencies:
				if not i.valid():
					print "%6.4g - invalid result"%i.freq
				else:
					target = self.frequency_angle_data[i.freq][1]
					print "%6.4g %6.2g %6.2g % 7.5g % 7.5g %7.5g %7.5g % 7.5g % 7.5g"%(int(i.freq), target, i.angle, i.gain, i.net(),i.swr(), i.real, i.imag, target-i.net())

	def parse(self, output):
		file = open(output, "rt")
		try : 
			lines = file.readlines()
		finally:
			file.close()
		i=0
		while i < len(lines):
			ln = lines[i].strip()
			if ln == "- - - - - - FREQUENCY - - - - - -":
				i = i+2
				freq = float(lines[i].strip()[10:-4])
				if not len(self.frequencies) or self.frequencies[-1].valid():
					self.frequencies.append(FrequencyData(self.char_imp))
				self.frequencies[-1].freq = freq
			elif ln == "- - - ANTENNA INPUT PARAMETERS - - -":
				i=i+4
				self.frequencies[-1].real = float(lines[i][60:72])
				self.frequencies[-1].imag = float(lines[i][72:84])
			elif ln =="- - - RADIATION PATTERNS - - -":
				i=i+5
				angle = 0
				freq = self.frequencies[-1].freq
				if freq in self.frequency_angle_data.keys():
					angle = self.frequency_angle_data[freq][0]
				while len(lines[i].strip()):
					ln = lines[i]
					theta = float(ln[0:8])
					phi = float(ln[8:17])
					if theta==90 and abs(phi-angle)<=self.angle_step*.5:
						self.frequencies[-1].gain = float(ln[28:36])-self.agt
						self.frequencies[-1].angle = angle
						break
					i = i+1
			i = i+1
		if self.frequency_angle_data:
			freqs = []
			for f in self.frequencies:
				if f.freq in self.frequency_angle_data.keys():
					freqs.append(f)
			self.frequencies = freqs

class NecFileObject:
	def __init__(self, options):
		self.vars = {}
		self.min_max = {}
		self.dependent_vars = []
		self.lines=[]
		self.varlines=[]
		self.paramlines={}
		self.source_tags={}
		self.autosegment=(0,0)
		self.frequency = 585
		self.output = options.output
		self.engine = options.engine
		self.sourcefile = options.input
		self.scale = 1
		self.angle_step = 5
		self.agt_correction= options.agt_correction
		self.min_wire_distance = options.min_wire_distance
		if self.sourcefile:
			self.readSource(self.sourcefile)
			try:
				if options.param_values_file:
					self.parseParameterValues(options.param_values_file)
					self.writeParametrized("output.nec")
			except AttributeError:
				pass

	def readSource(self, sourcefile):
		self.sourcefile = sourcefile
		file = open(sourcefile, "rt")
		try: self.lines = file.readlines()
		finally: file.close()
		if not self.lines: raise "Empty input file"
		self.parse()
	
	def parse(self):		
		self.vars = {}
		self.dependent_vars = []
		self.varlines=[]
		self.source_tags={}
		for i in xrange(len(self.lines)):
			ln = self.lines[i]
			comment = ln[ln.find("'")+1:]
			ln = ln[0:ln.find("'")].strip(' ')
			if ln[0:2]== "SY":
				try:
					d = {}
					exec(ln[3:].strip(), {}, d)
					self.vars.update(d)
					self.paramlines[d.keys()[0]]=i
					try:
						#strip the real comment from the comment
						min, max = eval(comment[0:comment.find("'")].strip(' '))
						self.min_max[d.keys()[0]]=(float(min),float(max))
					except:
						pass
				except:
					self.dependent_vars.append(ln[3:].strip())
			else:
				self.varlines.append(ln.replace(',',' ').split())
				if ln[0:2]=="EX":
					self.source_tags[int(self.varlines[-1][2])]=(len(self.varlines)-1,i)
				elif ln[0:2] == "FR":
					self.frequency = float(self.varlines[-1][5])
				elif ln[0:2] == "GS":
					self.scale = float(self.varlines[-1][3])
				elif ln[0:2] == "RP":
					self.angle_Step = float(self.varlines[-1][8])

		for i in self.vars.keys():
			self.vars[i]=float(self.vars[i])
	def parseParameterValues(self, file):
		try:
			f = open(file,"rt")
			lines = f.readlines()
			f.close()
		except:
			raise
		if len(lines)<2: raise  RuntimeError("invalid Parametes files")
		vars = lines[0].split()
		del lines[0]
		lines[0] = map(float, lines[0].split())
		opt_vars = {}
		for i in range(len(vars)):
			if vars[i] not in self.vars: raise RuntimeError("invalid Parameter name")
			self.vars[vars[i]] = lines[0][i]


	def parseAgt(self, output):
		file = open(output, "rt")
		try : 
			lines = file.readlines()
		finally:
			file.close()
		i=len(lines)-1
		tests = "   AVERAGE POWER GAIN="
		testl = len(tests)
		while i >0:
			if lines[i][0:testl]==tests:
				return float(lines[i][testl+1:].strip().split()[0].lower())
			i=i-1
		return 1

	def calcLength(self, line):
		return self.scale*necmath.sqrt(necmath.pow(line[2]-line[5],2)+necmath.pow(line[3]-line[6],2)+necmath.pow(line[4]-line[7],2))

	def autoSegment(self, line):
		nsegs = self.calcLength(line)*self.autosegment[0]/self.autosegment[1]
		line[1] = max(int(nsegs+.5),1)
		if line[0] in self.source_tags:
			line[1]=line[1]+2
			if line[1] % 2 == 0:
				line[1]=line[1]+1
			self.varlines[self.source_tags[line[0]][0]][3] = str(int(line[1]/2)+1)
			self.lines[self.source_tags[line[0]][1]] = " ".join(self.varlines[self.source_tags[line[0]][0]])
		

	def autoSegmentation(self, segs_per_halfwave=0, freq = None):
		if not freq: freq = self.frequency
		if not freq: freq = 585
		halfwave = 150.0/freq
		self.autosegment = (segs_per_halfwave, halfwave)
		
	def writeSource(self, filename):
		file = open(filename, "wt")
		try: file.writelines(self.lines)
		finally: file.close()
	
	def evalToken(self, x):
		return eval(x, necmath.__dict__,self.globals)

	def formatNumber(self, n):
		if type(n) == type(.1):
			return "%.7f"%n
		else:
			return str(n)
	
	def formatName(self, n):
		return "%8s"%n

	def testLineIntersection(self, tag1, tag2, line1, line2, r1, r2):
		if line1[0]==line2[0]:
			if line1[1]!=line2[1]:return 1
			else :	raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, 0))
		if line1[0]==line2[1]:
			if line1[1]!=line2[0]:return 1
			else :	raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, 0))
		if line1[1]==line2[0]:
			if line1[0]!=line2[1]:return 1
			else :	raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, 0))
		if line1[1]==line2[1]:
			if line1[0]!=line2[0]:return 1
			else :	raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, 0))
		#print "line1[0] = [%f, %f, %f]"%tuple(line1[0])
		#print "line1[1] = [%f, %f, %f]"%tuple(line1[1])
		#print "line2[0] = [%f, %f, %f]"%tuple(line2[0])
		#print "line2[1] = [%f, %f, %f]"%tuple(line2[1])
		v1 = v3sub(line1[1],line1[0])
		l = v3len(v1)
		if not l:
			raise RuntimeError("Line with 0 length (tag %d)"%tag1)
		v1 = v3mul(1.0/l,v1)
		v2 = v3sub(line2[1],line2[0])
		l = v3len(v2)
		if not l:
			raise RuntimeError("Line with 0 length (tag %d)"%tag2)
		v2 = v3mul(1.0/l,v2)
		n = v3unit(v3cross(v1,v2))
		#print "v1 = [%f, %f, %f]"%tuple(v1)
		#print "v2 = [%f, %f, %f]"%tuple(v2)
		#print "n  = [%f, %f, %f]"%tuple(n)
		if n[0]==0 and n[1]==0 and n[2]==0: #parallel
			v2 = v3sub(line2[1], line1[0])
			d = v3dot(v1,v2)
			pr = v3add(line1[0],v3mul(d, v1))
			pr = v3sub(line2[1],pr)
			pr = v3len(pr)
			if pr>r1+r2+self.min_wire_distance:
				return 1

			zerocount = 0
			v2 = v3sub(line2[0], line1[0])
			d = d * v3dot(v1,v2)
			if d < 0 :
				raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, pr))
			elif d == 0:
				zerocount = zerocount+1
			v2 = v3sub(line2[1], line1[1])
			d = v3dot(v1,v2)
			v2 = v3sub(line2[0], line1[1])
			d = d * v3dot(v1,v2)
			if d < 0 :
				raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, pr))
			elif d == 0:
				zerocount = zerocount+1

			v2 = v3sub(line1[1], line2[1])
			d = v3dot(v1,v2)
			v2 = v3sub(line1[0], line2[1])
			d = d * v3dot(v1,v2)
			if d < 0 :
				raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, pr))
			elif d == 0:
				zerocount = zerocount+1


			v2 = v3sub(line1[1], line2[0])
			d = v3dot(v1,v2)
			v2 = v3sub(line1[0], line2[0])
			d = d * v3dot(v1,v2)
			if d < 0 :
				raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, pr))
			elif d == 0:
				zerocount = zerocount+1

			if zerocount > 2 :
				raise RuntimeError("Overlapping lines (tag %d and tag %d, distance=%f)"%(tag1, tag2, pr))

			return 1

		s = v3sub(line1[0], line2[0])
		#print "s  = [%f, %f, %f]"%tuple(s)
		d = v3dot(n, s)
		#print "plane line distance = %f"%d
		if abs(d) > r1+r2 + self.min_wire_distance: #infinite lines are far enough
			return 1

		m = v3mul(d, n)
		l20 = v3sub(line2[0],m)
		l21 = v3sub(line2[1],m)
		#line2 and line1 are now in one plane

		c1 = v3cross(v3unit(v3sub(l20,line1[0])),v1)
		#print "c1 = [%f, %f, %f]"%tuple(c1)
		c2 = v3cross(v3unit(v3sub(l21,line1[0])),v1)
		#print "c2 = [%f, %f, %f]"%tuple(c2)
		dot1 = v3dot(c1, n)*v3dot(c2, n)
		c3 = v3cross(v3unit(v3sub(line1[0],l20)),v2)
		#print "c3 = [%f, %f, %f]"%tuple(c3)
		c4 = v3cross(v3unit(v3sub(line1[1],l20)),v2)
		#print "c4 = [%f, %f, %f]"%tuple(c4)
		dot2 = v3dot(c3, n)*v3dot(c4, n)
		#print (dot1, dot2)
		if dot1 < 0 and dot2 < 0:
				raise RuntimeError("Intersecting lines (tag %d and tag %d)"%(tag1, tag2))
		return 1
	def testLineIntersections(self, lines):
		nlines= len(lines)
		for i in range(nlines):
			for j in range(i+1,nlines):
				self.testLineIntersection(lines[i][0], lines[j][0], [lines[i][2:5],lines[i][5:8]], [lines[j][2:5],lines[j][5:8]], lines[i][8], lines[i][8])

		return 1

	def mirrorStructure(self, lines, tincr, x,y,z):
		#print "mirroring"
		l = len(lines)
		for i in range(l):
			lines.append(list(lines[i]))
			if lines[l+i][0]:
				lines[l+i][0]=lines[i][0]+tincr
			if x:
				lines[l+i][2]=-lines[i][2]
				lines[l+i][5]=-lines[i][5]
			if y:
				lines[l+i][3]=-lines[i][3]
				lines[l+i][6]=-lines[i][6]
			if z:
				lines[l+i][4]=-lines[i][4]
				lines[l+i][7]=-lines[i][7]

	def moveStructure(self, lines, rng, tincr, rx, ry,rz, x,y,z):
		#print "moving %d lines, from %d to %d, incrementing tags with %d"%(rng[1]-rng[0],rng[0],rng[1],tincr)
		rx = necmath.pi*rx/180
		ry = necmath.pi*ry/180
		rz = necmath.pi*rz/180
		for i in range(rng[0], rng[1]):
			if lines[i][0]:
				lines[i][0]+=tincr
			s = lines[i][2:5]
			e = lines[i][5:8]
			if rx:
				v3rotx(rx, s)
				v3rotx(rx, e)
			if ry:
				v3roty(ry, s)
				v3roty(ry, e)
			if rz:
				v3rotz(rz, s)
				v3rotz(rz, e)
			s[0]+=x
			s[1]+=y
			s[2]+=z
			e[0]+=x
			e[1]+=y
			e[2]+=z
			lines[i][2:5]=s
			lines[i][5:8]=e

	def moveCopyStructure(self, lines, tincr, new_structures, rx, ry,rz, x,y,z, from_tag):
		#print "moving %d lines, incrementing tags with %d, starting from tag %d"%(len(lines),tincr, from_tag)
		l = len(lines)
		rng = (0, l)
		if from_tag:
			for i in range(0,l):
				if lines[i][0]==from_tag:
					rng = (i,l)
					break
			if rng == (0,l) and lines[0][0]!=from_tag:
				return

		if not new_structures:
			self.moveStructure(lines, rng, tincr, rx,ry,rz,x,y,z)
			return

		while new_structures:
			new_structures = new_structures-1
			for i in range(rng[0],rng[1]):
				lines.append(list(lines[i]))

			rng = (l,len(lines))
			l = len(lines)
			self.moveStructure(lines, rng, tincr, rx,ry,rz,x,y,z)


	def rotateStructure(self, lines, tincr, nstructures):
		if nstructures<=1:
			return
		self.moveCopyStructure(lines, tincr, nstructures-1, 0, 0,360.0/nstructures, 0,0,0, 0)

	def necInputLines(self, skiptags=["FR", "XQ", "RP", "EN"]):
		lines=[]
		math_lines = []
		self.globals={}
		self.globals.update(self.vars)
		for d in self.dependent_vars:
			try: exec(d, necmath.__dict__, self.globals)
			except:
				print "failed parsing '%s'"%(d)
				raise
		for ln in self.varlines:
			if not ln: continue
			if ln[0].strip() != "GW":
				if ln[0].strip() not in skiptags:
					lines.append(" ".join(ln))
				if ln[0].strip() == "GX":
					self.mirrorStructure(math_lines, int(ln[1]), int(ln[2][0]), int(ln[2][1]), int(ln[2][2]))
				elif ln[0].strip() == "GM":
					if len(ln) < 9:
						ln=ln+(9-len(ln))*[.0]
					self.moveCopyStructure(math_lines, int(ln[1]), int(ln[2]), float(ln[3]), float(ln[4]), float(ln[5]),float(ln[6]), float(ln[7]), float(ln[8]), int(float(ln[9])))
				elif ln[0].strip() == "GR":
					self.rotateStructure(math_lines, int(ln[1]), int(ln[2]))
			else:
				sline = map( self.evalToken , ln[1:])
				math_lines.append(list(sline))
				if self.autosegment[0]:
					self.autoSegment(sline)
				sline = map(self.formatNumber, sline)
				sline.insert(0, ln[0])
				lines.append(" ".join(sline))
		del self.globals
		if not self.testLineIntersections(math_lines):
			return []
		return lines

	def writeNecInput(self, filename, extralines=[], skiptags=[]):
		lines = self.necInputLines(skiptags)
		if not lines: return 0
		lines.extend(extralines)
		file = open(filename, "wt")
		try: file.write("\n".join(lines))
		finally: file.close()
		return 1


	def writeParametrized(self, filename, extralines=[], skiptags=[], comments=[]):
		lines=[]
		self.globals={}
		self.globals.update(self.vars)
		for v in self.vars.keys():
			lno = self.paramlines[v]
			if v in self.min_max.keys():
				self.lines[lno] = "SY %s=%.7g ' %g, %g" %(v, self.vars[v], self.min_max[v][0], self.min_max[v][1])
			else:
				self.lines[lno] = "SY %s=%.7g" %(v, self.vars[v])
		for d in self.dependent_vars:
			try: exec(d, necmath.__dict__, self.globals)
			except:
				print "failed parsing '%s'"%(d)
				raise
		has_comments = 0
		for ln in self.lines:
			sl = ln.replace(',',' ').split()
			if sl and sl[0].strip() == "CE":
				has_comments=1
			if not sl or not self.autosegment[0] or sl[0].strip() != "GW" : 
				lines.append(ln.strip())
				continue
			if sl[0].strip() == "GW":
				sline = map( self.evalToken , sl[1:])
				self.autoSegment(sline)
				sl[2] = str(sline[1])
				lines.append(" ".join(sl))

		del self.globals
		lines.extend(extralines)
		file = open(filename, "wt")
		try: 
			if comments:
				file.write("CM ")
				file.write("\nCM ".join(comments))
				file.write("\n")
				if not has_comments:
					file.write("CE\n")
			file.write("\n".join(lines)+"\n")
		finally: file.close()
	def freqSweepLines(self, nec_input_lines, sweep):
		lines = list(nec_input_lines)
		#lines.append("FR 0 1 0 0 %g 0"%sweep[0])
		#lines.append("XQ")
		lines.append("FR 0 %d 0 0 %g %g"%(sweep[2],sweep[0],sweep[1]))
		lines.append("RP 0 1 73 1000 90 0 0 %d"%self.angle_step)
		lines.append("XQ")
		return lines
#		self.writeNecInput(filename, lines, ["FR", "XQ", "RP", "EN"])
	def agtLines(self, nec_input_lines, sweep):
		lines = []
		for line in nec_input_lines:
			if line[0:2]!="LD":
				lines.append(line)
		#lines.append("FR 0 1 0 0 %g 0"%sweep[0])
		#lines.append("XQ")
		#print "agt freq=%g"%(sweep[0]+(sweep[2]-1)*.5*sweep[1])
		lines.append("FR 0 0 0 0 %g 0"%(sweep[0]+(sweep[2]-1)*.5*sweep[1]))
		lines.append("RP 0 37 73 1001 -180 0 5 5")
		lines.append("XQ")
		return lines
	
	def runSweep(self, nec_input_lines, sweep):
		import tempfile as tmp
		import subprocess as sp
		import os
		try:
			os.mkdir(self.output)
		except: pass
		f, nec_input = tmp.mkstemp(".inp", "nec2", os.path.join(".",self.output) ,1)
		os.close(f)
		agt_input = nec_input[0:-3]+"agt"

		file = open(nec_input, "wt")
		try: file.write("\n".join(self.freqSweepLines(nec_input_lines,sweep)))
		finally: file.close()
		if self.agt_correction:
			file = open(agt_input, "wt")
			try: file.write("\n".join(self.agtLines(nec_input_lines,sweep)))
			finally: file.close()
		
		f, nec_output = tmp.mkstemp(".out", "nec2", os.path.join(".",self.output) ,1)
		os.close(f)
		f, exe_input = tmp.mkstemp(".cin", "nec2", os.path.join(".",self.output) ,1)
		os.close(f)
		agt = 1.0
		if self.agt_correction:
			f = open(exe_input,"wt")
			f.write(agt_input)
			f.write("\n")
			f.write(nec_output)
			f.write("\n")
			f.close()
			f = open(exe_input)
			popen = sp.Popen(self.engine, stdin=f, stdout=open(os.devnull))
			popen.wait()
			f.close()
			agt = self.parseAgt(nec_output)
			#print "sweep (%g,%d,%g) - AGT=%g (%g)"%(sweep[0],sweep[1],sweep[2],agt,10*math.log10(agt))
		f = open(exe_input,"wt")
		f.write(nec_input)
		f.write("\n")
		f.write(nec_output)
		f.write("\n")
		f.close()
		f = open(exe_input)
		popen = sp.Popen(self.engine, stdin=f, stdout=open(os.devnull))
		popen.wait()
		f.close()
		return (nec_output,agt)
		
	def runSweepT(self, nec_input_lines, sweep, number, result_map, result_lock, id ):
		try:
			r = self.runSweep(nec_input_lines,sweep)
		except:
			print sys.exc_info()[1]
			return
		result_lock.acquire()
		try: result_map[number]=(r[0],id,r[1])
		finally: result_lock.release()

	def runSweeps(self, sweeps, num_cores=1, cleanup=0):
		if cleanup:
			import os, time, stat
			try:
				ldir = os.listdir(self.output)
				n = time.time()
				for f in ldir:
					try:
						f = os.path.join(self.output,f)
						s = os.stat(f)
						if s[stat.ST_MTIME] + 180 < n:
							os.remove(f)
					except:
						pass
			except:
				pass

		total_freqs = 0
		for i in sweeps:
			total_freqs = total_freqs+i[2]
		if total_freqs < num_cores : 
			num_cores = max(total_freqs/2,1)
		freqs_per_core = total_freqs/num_cores
		cores_per_sweep = [0]*len(sweeps)
		while num_cores:
			for i in xrange(len(sweeps)):
				if cores_per_sweep[i]: continue
				if sweeps[i][2] < freqs_per_core:
					cores_per_sweep[i] =  1 
					total_freqs = total_freqs - sweeps[i][2]
					num_cores = num_cores-1
					if not num_cores: break
				else:
					cores_per_sweep[i] = 0 
		
			if not num_cores:
				for i in xrange(len(sweeps)):
					if cores_per_sweep[i]: continue
					cores_per_sweep[i] = 1
				break
			if freqs_per_core == total_freqs/num_cores:
				for i in xrange(len(sweeps)):
					if cores_per_sweep[i]: continue
					cores_per_sweep[i] =  int(sweeps[i][2]/freqs_per_core) 
				break
			freqs_per_core = total_freqs/num_cores

		
		results={}
		number=0
		try:
			nec_input_lines = self.necInputLines()
		except:
			print sys.exc_info()[1]
			return

		from threading import Lock, Thread
		result_lock = Lock()
		threads = []
		for i in xrange(len(sweeps)):
			ncores = cores_per_sweep[i]
		
			sweep = sweeps[i]
			fps = sweep[2]/ncores
			for j in xrange(ncores):
				s = [sweep[0]+j*fps*sweep[1],sweep[1],fps]
				if j==ncores-1:
					s = [sweep[0]+j*fps*sweep[1],sweep[1],sweep[2]-j*fps]
				threads.append(Thread(target=self.runSweepT, args=(nec_input_lines, s, number,results, result_lock,i )))
				threads[-1].start()
				number = number+1

		for t in threads:
			t.join()

		r = []
		for i in xrange(len(results)):
			r.append(results[i])
		return r

	def evaluate(self, sweeps, char_impedance, num_cores=1, cleanup=0, frequency_data = {}):
		NOP = NecOutputParser 
		results = self.runSweeps(sorted(sweeps), num_cores, cleanup) #[[174,6,8],[470,6,40]]
		print "Input file : %s"%self.sourcefile 
		print "Freq sweeps: %s"%str(sweeps)
		if self.autosegment[0]:
			print "Autosegmentation: %d per %g"%self.autosegment
		else:
			"Autosegmentation: NO"
		print "\n"
	
		for r in range(len(results)):
			nop = NOP(results[r][0], results[r][2], char_impedance, self.angle_step, frequency_data)
			nop.printFreqs(r==0)


import optparse 
class OptionParser(optparse.OptionParser):
	def __init__(self):
		optparse.OptionParser.__init__(self)
		self.add_option("-o", "--output-dir", type="string", metavar="DIR", dest="output", default=output, help="output path [%default]")
		self.add_option("-i", "--input", type="string", metavar="NEC_FILE", dest="input", default="", help="input nec file")
		self.add_option("-s", "--sweep", type="string", metavar="SWEEP", action="append", dest="sweeps", help="adds a sweep range e.g. -s (174,6,8) for vhf-hi freqs")
		self.add_option("-C", "--char-impedance", type="float", metavar="IMPEDANCE", default=300.0, help="The default is %default Ohms.")
		self.add_option("-u", "--uhf", "--uhf-52", action="append_const", dest="sweeps", const="(470,6,40)", help="adds a uhf (ch. 14-52) sweep")
		self.add_option("-U", "--uhf-69", action="append_const", dest="sweeps", const="(470,6,57)", help="adds a uhf (ch. 14-69) sweep")
		self.add_option("-V", "--vhf-hi", action="append_const", dest="sweeps", const="(174,6,8)", help="adds a vhf-hi (ch. 7-13) sweep")
		self.add_option("-v", "--vhf-lo", action="append_const", dest="sweeps", const="(54,6,6)", help="adds a vhf-lo (ch. 1-6) sweep")
		self.add_option("-n", "--num-cores", type="int", default=ncores, help="number of cores to be used, default=%default")
		self.add_option("-a", "--auto-segmentation", metavar="NUM_SEGMENTS", type="int", default=autosegmentation, help="autosegmentation level - set to 0 to turn autosegmentation off, default=%default")
		self.add_option("-e", "--engine", metavar="NEC_ENGINE", default="nec2dxs1k5.exe", help="nec engine file name, default=%default")
		self.add_option("-d", "--min-wire-distance", default=".005", type="float", help="minimum surface-to-surface distance allowed between non-connecting wires, default=%default")
	def parse_args(self):
		options, args = optparse.OptionParser.parse_args(self)
		if options.input == "":
			if len(args):
				options.input=args[0]
				del args[0]
			else:
				options.input = input
		if options.sweeps:
			options.sweeps = map(eval,options.sweeps)
		return (options, args)

def optionParser():
	class MainOptionParser(OptionParser):
		def __init__(self):
			OptionParser.__init__(self)
			self.add_option("--param-values-file", default="", help="Read the parameter values from file, generate output.nec and evaluate it instead of the input file. The file should contain two lines: space separated parameter name son the first and space separated values on the second.")
			self.add_option("--agt-correction", default="1", type="int", help="set to 0 to disable agt correction. It is faster but less accurate.")
			self.add_option("-c", "--centers", default=True, help="run sweep on the channel centers",action="store_false", dest="ends")
			self.add_option("-f", "--frequency_data", default = "{}", help="a map of frequency to (angle, expected_gain) tuple" )
		def parse_args(self):
			options, args = OptionParser.parse_args(self)
			options.frequency_data = eval(options.frequency_data)
			if not options.sweeps:
				options.sweeps = [(470,6,40)]
			if not options.ends:
				for i in range(len(options.sweeps)):
					if not options.sweeps[i][1]: continue
					options.sweeps[i] = (options.sweeps[i][0] - options.sweeps[i][1]/2, options.sweeps[i][1], options.sweeps[i][2]+1)
			return (options, args)
	return MainOptionParser()


def run(options):
	nf = NecFileObject(options)
	nf.autoSegmentation(options.auto_segmentation)
	nf.evaluate(options.sweeps, options.char_impedance, options.num_cores, 0, options.frequency_data)

def main():
#default values
	options, args = optionParser().parse_args()
	run(options)
	for inp in args:
		if inp[0]!="-":
			options.input = inp
			try:
				run(options)
			except:
				pass
	


if __name__ == "__main__":
	main()
